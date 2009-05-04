import py
from pypy.tool.pairtype import extendabletype
from pypy.rpython.ootypesystem import ootype
from pypy.translator.cli import dotnet
from pypy.translator.cli.dotnet import CLR
from pypy.translator.cli import opcodes
from pypy.jit.metainterp import history
from pypy.jit.metainterp.history import AbstractValue, Const
from pypy.jit.metainterp.resoperation import rop, opname
from pypy.jit.backend.cli.methodfactory import get_method_wrapper

System = CLR.System
OpCodes = System.Reflection.Emit.OpCodes
LoopDelegate = CLR.pypy.runtime.LoopDelegate
InputArgs = CLR.pypy.runtime.InputArgs

cVoid = ootype.nullruntimeclass


class __extend__(AbstractValue):
    __metaclass__ = extendabletype

    def getCliType(self):
        if self.type == history.INT:
            return dotnet.typeof(System.Int32)
        elif self.type == history.OBJ:
            return dotnet.typeof(System.Object)
        else:
            assert False, 'Unknown type: %s' % self.type

    def load(self, meth):
        v = meth.var_for_box(self)
        meth.il.Emit(OpCodes.Ldloc, v)

    def store(self, meth):
        v = meth.var_for_box(self)
        meth.il.Emit(OpCodes.Stloc, v)


class __extend__(Const):
    __metaclass__ = extendabletype

    def load(self, meth):
        raise NotImplementedError

    def store(self, meth):
        assert False, 'cannot store() to Constant'


class MethodArgument(AbstractValue):
    def __init__(self, index, cliType):
        self.index = index
        self.cliType = cliType

    def getCliType(self):
        return self.cliType

    def load(self, meth):
        if self.index == 0:
            meth.il.Emit(OpCodes.Ldarg_0)
        elif self.index == 1:
            meth.il.Emit(OpCodes.Ldarg_1)
        elif self.index == 2:
            meth.il.Emit(OpCodes.Ldarg_2)
        elif self.index == 3:
            meth.il.Emit(OpCodes.Ldarg_3)
        else:
            meth.il.Emit(OpCodes.Ldarg, self.index)

    def store(self, meth):
        meth.il.Emit(OpCodes.Starg, self.index)

    def __repr__(self):
        return "MethodArgument(%d)" % self.index


class Method(object):

    operations = [] # overwritten at the end of the module

    def __init__(self, cpu, name, loop):
        self.cpu = cpu
        self.name = name
        self.loop = loop
        self.boxes = {} # box --> local var
        self.meth_wrapper = self._get_meth_wrapper()
        self.il = self.meth_wrapper.get_il_generator()
        self.av_consts = MethodArgument(0, System.Type.GetType("System.Object[]"))
        self.av_inputargs = MethodArgument(1, dotnet.typeof(InputArgs))
        self.emit_load_inputargs()
        self.emit_operations()
        self.emit_end()
        delegatetype = dotnet.typeof(LoopDelegate)
        consts = dotnet.new_array(System.Object, 0)
        self.func = self.meth_wrapper.create_delegate(delegatetype, consts)


    def _get_meth_wrapper(self):
        restype = dotnet.class2type(cVoid)
        args = self._get_args_array([dotnet.typeof(InputArgs)])
        return get_method_wrapper(self.name, restype, args)

    def _get_args_array(self, arglist):
        array = dotnet.new_array(System.Type, len(arglist)+1)
        array[0] = System.Type.GetType("System.Object[]")
        for i in range(len(arglist)):
            array[i+1] = arglist[i]
        return array

    def var_for_box(self, box):
        try:
            return self.boxes[box]
        except KeyError:
            v = self.il.DeclareLocal(box.getCliType())
            self.boxes[box] = v
            return v

    def get_inputarg_field(self, type):
        t = dotnet.typeof(InputArgs)
        if type == history.INT:
            fieldname = 'ints'
        elif type == history.OBJ:
            fieldname = 'objs'
        else:
            assert False, 'Unknown type %s' % type
        return t.GetField(fieldname)        

    def load_inputarg(self, i, type, clitype):
        field = self.get_inputarg_field(type)
        self.av_inputargs.load(self)
        self.il.Emit(OpCodes.Ldfld, field)
        self.il.Emit(OpCodes.Ldc_I4, i)
        self.il.Emit(OpCodes.Ldelem, clitype)

    def store_inputarg(self, i, type, clitype, valuebox):
        field = self.get_inputarg_field(type)
        self.av_inputargs.load(self)
        self.il.Emit(OpCodes.Ldfld, field)
        self.il.Emit(OpCodes.Ldc_I4, i)
        valuebox.load(self)
        self.il.Emit(OpCodes.Stelem, clitype)

    def emit_load_inputargs(self):
        i = 0
        for box in self.loop.inputargs:
            self.load_inputarg(i, box.type, box.getCliType())
            box.store(self)
            i+=1

    def emit_operations(self):
        for op in self.loop.operations:
            func = self.operations[op.opnum]
            assert func is not None
            func(self, op)

    def emit_end(self):
        self.il.Emit(OpCodes.Ret)

    # -----------------------------

    def push_all_args(self, op):
        for box in op.args:
            box.load(self)

    def store_result(self, op):
        op.result.store(self)

    def emit_op_fail(self, op):
        i = 0
        for box in op.args:
            self.store_inputarg(i, box.type, box.getCliType(), box)
            i+=1
        self.il.Emit(OpCodes.Ret)

    def not_implemented(self, op):
        raise NotImplementedError

    emit_op_guard_value = not_implemented
    emit_op_cast_int_to_ptr = not_implemented
    emit_op_guard_nonvirtualized = not_implemented
    emit_op_setarrayitem_gc = not_implemented
    emit_op_guard_false = not_implemented
    emit_op_unicodelen = not_implemented
    emit_op_jump = not_implemented
    emit_op_setfield_raw = not_implemented
    emit_op_cast_ptr_to_int = not_implemented
    emit_op_guard_no_exception = not_implemented
    emit_op_newunicode = not_implemented
    emit_op_new_array = not_implemented
    emit_op_unicodegetitem = not_implemented
    emit_op_strgetitem = not_implemented
    emit_op_getfield_raw = not_implemented
    emit_op_setfield_gc = not_implemented
    emit_op_oosend_pure = not_implemented
    emit_op_getarrayitem_gc_pure = not_implemented
    emit_op_arraylen_gc = not_implemented
    emit_op_guard_true = not_implemented
    emit_op_unicodesetitem = not_implemented
    emit_op_getfield_raw_pure = not_implemented
    emit_op_new_with_vtable = not_implemented
    emit_op_getfield_gc_pure = not_implemented
    emit_op_guard_class = not_implemented
    emit_op_getarrayitem_gc = not_implemented
    emit_op_getfield_gc = not_implemented
    emit_op_call_pure = not_implemented
    emit_op_strlen = not_implemented
    emit_op_newstr = not_implemented
    emit_op_guard_exception = not_implemented
    emit_op_call = not_implemented
    emit_op_strsetitem = not_implemented


# --------------------------------------------------------------------
    
# the follwing functions automatically build the various emit_op_*
# operations based on the definitions in translator/cli/opcodes.py

def make_operation_list():
    operations = [None] * (rop._LAST+1)
    for key, value in rop.__dict__.items():
        key = key.lower()
        if key.startswith('_'):
            continue
        methname = 'emit_op_%s' % key
        if hasattr(Method, methname):
            func = getattr(Method, methname).im_func
        else:
            instrlist = opcodes.opcodes[key]
            func = render_op(methname, instrlist)
        operations[value] = func
    return operations

def render_op(methname, instrlist):
    lines = []
    for instr in instrlist:
        if instr == opcodes.PushAllArgs:
            lines.append('self.push_all_args(op)')
        elif instr == opcodes.StoreResult:
            lines.append('self.store_result(op)')
        else:
            if not isinstance(instr, str):
                print 'WARNING: unknown instruction %s' % instr
                return

            if instr.startswith('call '):
                signature = instr[len('call '):]
                renderCall(lines, signature)
            else:
                attrname = opcode2attrname(instr)
                lines.append('self.il.Emit(OpCodes.%s)' % attrname)
    body = py.code.Source('\n'.join(lines))
    src = body.putaround('def %s(self, op):' % methname)
    dic = {'OpCodes': OpCodes,
           'System': System,
           'dotnet': dotnet}
    exec src.compile() in dic
    return dic[methname]

def opcode2attrname(opcode):
    if opcode == 'ldc.r8 0':
        return 'Ldc_R8, 0' # XXX this is a hack
    if opcode == 'ldc.i8 0':
        return 'Ldc_I8, 0' # XXX this is a hack
    parts = map(str.capitalize, opcode.split('.'))
    return '_'.join(parts)

def renderCall(body, signature):
    # signature is like this:
    # int64 class [mscorlib]System.Foo::Bar(int64, int32)

    typenames = {
        'int32': 'System.Int32',
        'int64': 'System.Int64',
        'float64': 'System.Double',
        }
    
    restype, _, signature = signature.split(' ', 3)
    assert signature.startswith('[mscorlib]'), 'external assemblies '\
                                               'not supported'
    signature = signature[len('[mscorlib]'):]
    typename, signature = signature.split('::')
    methname, signature = signature.split('(')
    assert signature.endswith(')')
    params = signature[:-1].split(',')
    params = map(str.strip, params)
    params = [typenames.get(p, p) for p in params]
    params = ['dotnet.typeof(%s)' % p for p in params]

    body.append("t = System.Type.GetType('%s')" % typename)
    body.append("params = dotnet.init_array(System.Type, %s)" % ', '.join(params))
    body.append("methinfo = t.GetMethod('%s', params)" % methname)
    body.append("self.il.Emit(OpCodes.Call, methinfo)")

Method.operations = make_operation_list()
