import ctypes
import threading

from .vdtui import *

option('min_memory_mb', 0, 'minimum memory to continue loading and async processing')

Sheet.addCommand('^C', 'cancel-sheet', 'cancelThread(*sheet.currentThreads or error("no active threads on this sheet"))')
globalCommand('g^C', 'cancel-all', 'cancelThread(*vd.threads or error("no threads"))')
globalCommand('^T', 'threads-all', 'vd.push(vd.threadsSheet)')

def cancelThread(*threads, exception=EscapeException):
    'Raise exception on another thread.'
    for t in threads:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(t.ident), ctypes.py_object(exception))


SheetsSheet.addCommand('^C', 'cancel-sheet', 'cancelThread(*cursorRow.currentThreads)')

SheetsSheet.columns += [
    ColumnAttr('threads', 'currentThreads', type=len),
]

# each row is an augmented threading.Thread object
class ThreadsSheet(Sheet):
    rowtype = 'threads'
    columns = [
        ColumnAttr('name'),
        Column('process_time', type=float, getter=lambda col,row: elapsed_s(row)),
        ColumnAttr('profile'),
        ColumnAttr('status'),
        ColumnAttr('exception'),
    ]
    def reload(self):
        self.rows = vd().threads

ThreadsSheet.addCommand('^C', 'cancel-thread', 'cancelThread(cursorRow)')

def elapsed_s(t):
    return (t.endTime or time.process_time())-t.startTime

def checkMemoryUsage(vs):
    min_mem = options.min_memory_mb
    if min_mem and vd().unfinishedThreads:
        tot_m, used_m, free_m = map(int, os.popen('free --total --mega').readlines()[-1].split()[1:])
        ret = '[%dMB]' % free_m
        if free_m < min_mem:
            attr = 'red'
            status('%dMB free < %dMB minimum, stopping threads' % (free_m, min_mem))
            cancelThread(*vd().unfinishedThreads)
            curses.flash()
        else:
            attr = 'green'
        return ret, attr

vd().threadsSheet = ThreadsSheet('thread_history')
vd().addHook('rstatus', checkMemoryUsage)
