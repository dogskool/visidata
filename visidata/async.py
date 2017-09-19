import ctypes
import threading
import pstats
import cProfile

from .vdtui import *

min_task_time_s = 0.10 # only keep tasks that take longer than this number of seconds

option('profile_tasks', True, 'profile async tasks')
option('min_memory_mb', 0, 'minimum memory to continue loading and async processing')

globalCommand('^C', 'if sheet.currentThreads: ctypeAsyncRaise(sheet.currentThreads[-1], EscapeException)', 'cancel most recent task on the current sheet')
globalCommand('^T', 'vd.push(vd.tasksSheet)', 'push task history sheet')
globalCommand('^O', 'toggleProfiling(vd)', 'turn profiling on for main process')

class ProfileSheet(TextSheet):
    commands = TextSheet.commands + [
        Command('z^S', 'profile.dump_stats(input("save profile to: ", value=name+".prof"))', 'save profile'),
    ]
    def __init__(self, name, pr):
        super().__init__(name, getProfileResults(pr))
        self.profile = pr

vd().profile = None
def toggleProfiling(vd):
    if not vd.profile:
        vd.profile = cProfile.Profile()
        vd.profile.enable()
        vd.status('profiling of main task enabled')
    else:
        vd.profile.disable()
        vs = ProfileSheet("main_profile", vd.profile)
        vd.push(vs)
        vd.profile = None
        vd.status('profiling of main task disabled')


# define @async for potentially long-running functions
#   when function is called, instead launches a thread
#   ENTER on that row pushes a profile of the thread

@functools.wraps(vd().toplevelTryFunc)
def threadProfileCode(vdself, func, *args, **kwargs):
    'Profile @async tasks if `options.profile_tasks` is set.'
    thread = threading.current_thread()
    if options.profile_tasks:
        pr = cProfile.Profile()
        pr.enable()
        ret = threadProfileCode.__wrapped__(vdself, func, *args, **kwargs)
        thread.profile = pr
        pr.disable()
    else:
        ret = threadProfileCode.__wrapped__(vdself, func, *args, **kwargs)

    # remove very-short-lived async actions
    if elapsed_s(thread) < min_task_time_s:
        vd().threads.remove(thread)

    return ret

def getProfileResults(pr):
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s)
    ps.strip_dirs()
    ps.sort_stats('cumulative')
    ps.print_stats()
    return s.getvalue()

def ctypeAsyncRaise(threadObj, exception):
    'Raise exception on another thread.'

    def dictFind(D, value):
        'Return first key in dict `D` corresponding to `value`.'
        for k, v in D.items():
            if v is value:
                return k

    # Following `ctypes call follows https://gist.github.com/liuw/2407154.
    thread = dictFind(threading._active, threadObj)
    if thread:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread), ctypes.py_object(exception))
        status('canceling %s' % threadObj.name)
    else:
        status('no thread to cancel')


# each row is an augmented threading.Thread object
class TasksSheet(Sheet):
    commands = [
        Command('^C', 'ctypeAsyncRaise(cursorRow, EscapeException)', 'cancel this action'),
        Command(ENTER, 'vd.push(ProfileSheet(cursorRow.name+"_profile", cursorRow.profile))', 'push profile sheet for this action'),
    ]
    columns = [
        ColumnAttr('name'),
        Column('elapsed_s', type=float, getter=lambda r: elapsed_s(r)),
        Column('status', getter=lambda r: r.status),
    ]
    def reload(self):
        self.rows = vd().threads

def elapsed_s(t):
    return (t.endTime or time.process_time())-t.startTime

@functools.wraps(vd().rightStatus)
def checkMemoryUsage(vs):
    ret, attr = checkMemoryUsage.__wrapped__(vs)   # prev rightStatus
    min_mem = options.min_memory_mb
    if min_mem and vd().unfinishedThreads:
        tot_m, used_m, free_m = map(int, os.popen('free --total --mega').readlines()[-1].split()[1:])
        ret = '[%dMB] %s' % (free_m, ret)
        if free_m < min_mem:
            attr = colors['red']
            status('%dMB free < %dMB minimum, stopping threads' % (free_m, min_mem))
            for t in vd().threads:
                if t.is_alive():
                    ctypeAsyncRaise(t, EscapeException)
    return ret, attr

vd().tasksSheet = TasksSheet('task_history')
vd().toplevelTryFunc = threadProfileCode
vd().rightStatus = checkMemoryUsage

