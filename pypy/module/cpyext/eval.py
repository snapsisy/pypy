from pypy.interpreter.error import OperationError
from pypy.interpreter.astcompiler import consts
from rpython.rtyper.lltypesystem import rffi, lltype
from pypy.module.cpyext.api import (
    cpython_api, CANNOT_FAIL, CONST_STRING, FILEP, fread, feof, Py_ssize_tP,
    cpython_struct, is_valid_fp)
from pypy.module.cpyext.pyobject import PyObject, as_pyobj, as_xpyobj
from pypy.module.cpyext.pyerrors import PyErr_SetFromErrno
from pypy.module.cpyext.funcobject import PyCodeObject
from pypy.module.__builtin__ import compiling

PyCompilerFlags = cpython_struct(
    "PyCompilerFlags", (("cf_flags", rffi.INT),))
PyCompilerFlagsPtr = lltype.Ptr(PyCompilerFlags)

PyCF_MASK = (consts.CO_FUTURE_DIVISION | 
             consts.CO_FUTURE_ABSOLUTE_IMPORT |
             consts.CO_FUTURE_WITH_STATEMENT |
             consts.CO_FUTURE_PRINT_FUNCTION |
             consts.CO_FUTURE_UNICODE_LITERALS)

@cpython_api([PyObject, PyObject, PyObject], PyObject)
def PyEval_CallObjectWithKeywords(space, w_obj, w_arg, w_kwds):
    return space.call(w_obj, w_arg, w_kwds)

@cpython_api([], PyObject)
def PyEval_GetBuiltins(space):
    """Return a dictionary of the builtins in the current execution
    frame, or the interpreter of the thread state if no frame is
    currently executing."""
    caller = space.getexecutioncontext().gettopframe_nohidden()
    if caller is not None:
        w_globals = caller.w_globals
        w_builtins = space.getitem(w_globals, space.wrap('__builtins__'))
        if not space.isinstance_w(w_builtins, space.w_dict):
            w_builtins = w_builtins.getdict(space)
    else:
        w_builtins = space.builtin.getdict(space)
    return as_pyobj(space, w_builtins)   # borrowed

@cpython_api([], PyObject, error=CANNOT_FAIL)
def PyEval_GetLocals(space):
    """Return a dictionary of the local variables in the current execution
    frame, or NULL if no frame is currently executing."""
    caller = space.getexecutioncontext().gettopframe_nohidden()
    if caller is None:
        w_res = None
    else:
        w_res = caller.getdictscope()
    return as_xpyobj(space, w_res)    # borrowed

@cpython_api([], PyObject, error=CANNOT_FAIL)
def PyEval_GetGlobals(space):
    """Return a dictionary of the global variables in the current execution
    frame, or NULL if no frame is currently executing."""
    caller = space.getexecutioncontext().gettopframe_nohidden()
    if caller is None:
        w_res = None
    else:
        w_res = caller.w_globals
    return as_xpyobj(space, w_res)    # borrowed

@cpython_api([PyCodeObject, PyObject, PyObject], PyObject)
def PyEval_EvalCode(space, w_code, w_globals, w_locals):
    """This is a simplified interface to PyEval_EvalCodeEx(), with just
    the code object, and the dictionaries of global and local variables.
    The other arguments are set to NULL."""
    if w_globals is None:
        w_globals = space.w_None
    if w_locals is None:
        w_locals = space.w_None
    return compiling.eval(space, w_code, w_globals, w_locals)

@cpython_api([PyObject, PyObject], PyObject)
def PyObject_CallObject(space, w_obj, w_arg):
    """
    Call a callable Python object callable_object, with arguments given by the
    tuple args.  If no arguments are needed, then args may be NULL.  Returns
    the result of the call on success, or NULL on failure.  This is the equivalent
    of the Python expression apply(callable_object, args) or
    callable_object(*args)."""
    return space.call(w_obj, w_arg)

@cpython_api([PyObject, PyObject, PyObject], PyObject)
def PyObject_Call(space, w_obj, w_args, w_kw):
    """
    Call a callable Python object, with arguments given by the
    tuple args, and named arguments given by the dictionary kw. If no named
    arguments are needed, kw may be NULL. args must not be NULL, use an
    empty tuple if no arguments are needed. Returns the result of the call on
    success, or NULL on failure.  This is the equivalent of the Python expression
    apply(callable_object, args, kw) or callable_object(*args, **kw)."""
    return space.call(w_obj, w_args, w_kw)

# These constants are also defined in include/eval.h
Py_single_input = 256
Py_file_input = 257
Py_eval_input = 258

def compile_string(space, source, filename, start, flags=0):
    w_source = space.wrap(source)
    start = rffi.cast(lltype.Signed, start)
    if start == Py_file_input:
        mode = 'exec'
    elif start == Py_eval_input:
        mode = 'eval'
    elif start == Py_single_input:
        mode = 'single'
    else:
        raise OperationError(space.w_ValueError, space.wrap(
            "invalid mode parameter for compilation"))
    return compiling.compile(space, w_source, filename, mode, flags)

def run_string(space, source, filename, start, w_globals, w_locals):
    w_code = compile_string(space, source, filename, start)
    return compiling.eval(space, w_code, w_globals, w_locals)

@cpython_api([CONST_STRING], rffi.INT_real, error=-1)
def PyRun_SimpleString(space, command):
    """This is a simplified interface to PyRun_SimpleStringFlags() below,
    leaving the PyCompilerFlags* argument set to NULL."""
    command = rffi.charp2str(command)
    run_string(space, command, "<string>", Py_file_input,
               space.w_None, space.w_None)
    return 0

@cpython_api([CONST_STRING, rffi.INT_real,PyObject, PyObject], PyObject)
def PyRun_String(space, source, start, w_globals, w_locals):
    """This is a simplified interface to PyRun_StringFlags() below, leaving
    flags set to NULL."""
    source = rffi.charp2str(source)
    filename = "<string>"
    return run_string(space, source, filename, start, w_globals, w_locals)

@cpython_api([rffi.CCHARP, rffi.INT_real, PyObject, PyObject,
              PyCompilerFlagsPtr], PyObject)
def PyRun_StringFlags(space, source, start, w_globals, w_locals, flagsptr):
    """Execute Python source code from str in the context specified by the
    dictionaries globals and locals with the compiler flags specified by
    flags.  The parameter start specifies the start token that should be used to
    parse the source code.

    Returns the result of executing the code as a Python object, or NULL if an
    exception was raised."""
    source = rffi.charp2str(source)
    if flagsptr:
        flags = rffi.cast(lltype.Signed, flagsptr.c_cf_flags)
    else:
        flags = 0
    w_code = compile_string(space, source, "<string>", start, flags)
    return compiling.eval(space, w_code, w_globals, w_locals)

@cpython_api([FILEP, CONST_STRING, rffi.INT_real, PyObject, PyObject], PyObject)
def PyRun_File(space, fp, filename, start, w_globals, w_locals):
    """This is a simplified interface to PyRun_FileExFlags() below, leaving
    closeit set to 0 and flags set to NULL."""
    BUF_SIZE = 8192
    source = ""
    filename = rffi.charp2str(filename)
    buf = lltype.malloc(rffi.CCHARP.TO, BUF_SIZE, flavor='raw')
    if not is_valid_fp(fp):
        lltype.free(buf, flavor='raw')
        PyErr_SetFromErrno(space, space.w_IOError)
        return None
    try:
        while True:
            count = fread(buf, 1, BUF_SIZE, fp)
            count = rffi.cast(lltype.Signed, count)
            source += rffi.charpsize2str(buf, count)
            if count < BUF_SIZE:
                if feof(fp):
                    break
                PyErr_SetFromErrno(space, space.w_IOError)
    finally:
        lltype.free(buf, flavor='raw')
    return run_string(space, source, filename, start, w_globals, w_locals)

# Undocumented function!
@cpython_api([PyObject, Py_ssize_tP], rffi.INT_real, error=0)
def _PyEval_SliceIndex(space, w_obj, pi):
    """Extract a slice index from a PyInt or PyLong or an object with the
    nb_index slot defined, and store in *pi.
    Silently reduce values larger than PY_SSIZE_T_MAX to PY_SSIZE_T_MAX,
    and silently boost values less than -PY_SSIZE_T_MAX-1 to -PY_SSIZE_T_MAX-1.

    Return 0 on error, 1 on success.

    Note:  If v is NULL, return success without storing into *pi.  This
    is because_PyEval_SliceIndex() is called by apply_slice(), which can be
    called by the SLICE opcode with v and/or w equal to NULL.
    """
    if w_obj is not None:
        pi[0] = space.getindex_w(w_obj, None)
    return 1

@cpython_api([rffi.CCHARP, rffi.CCHARP, rffi.INT_real, PyCompilerFlagsPtr],
             PyObject)
def Py_CompileStringFlags(space, source, filename, start, flagsptr):
    """Parse and compile the Python source code in str, returning the
    resulting code object.  The start token is given by start; this
    can be used to constrain the code which can be compiled and should
    be Py_eval_input, Py_file_input, or Py_single_input.  The filename
    specified by filename is used to construct the code object and may
    appear in tracebacks or SyntaxError exception messages.  This
    returns NULL if the code cannot be parsed or compiled."""
    source = rffi.charp2str(source)
    filename = rffi.charp2str(filename)
    if flagsptr:
        flags = rffi.cast(lltype.Signed, flagsptr.c_cf_flags)
    else:
        flags = 0
    return compile_string(space, source, filename, start, flags)

@cpython_api([PyCompilerFlagsPtr], rffi.INT_real, error=CANNOT_FAIL)
def PyEval_MergeCompilerFlags(space, cf):
    """This function changes the flags of the current evaluation
    frame, and returns true on success, false on failure."""
    flags = rffi.cast(lltype.Signed, cf.c_cf_flags)
    result = flags != 0
    current_frame = space.getexecutioncontext().gettopframe_nohidden()
    if current_frame:
        codeflags = current_frame.pycode.co_flags
        compilerflags = codeflags & PyCF_MASK
        if compilerflags:
            result = 1
            flags |= compilerflags
        # No future keyword at the moment
        # if codeflags & CO_GENERATOR_ALLOWED:
        #     result = 1
        #     flags |= CO_GENERATOR_ALLOWED
    cf.c_cf_flags = rffi.cast(rffi.INT, flags)
    return result

        
