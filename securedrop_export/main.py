import os
import shutil
import platform
import logging
import sys
import subprocess

from securedrop_export.archive import Archive, Metadata
from securedrop_export.enums import Command, ExportEnum

from securedrop_export.disk.service import Service as ExportService
from securedrop_export.print.service import Service as PrintService

from logging.handlers import TimedRotatingFileHandler, SysLogHandler
from securedrop_export import __version__
from securedrop_export.utils import safe_mkdir

CONFIG_PATH = "/etc/sd-export-config.json"
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".securedrop_export")
LOG_DIR_NAME = "logs"
EXPORT_LOG_FILENAME = "export.log"

logger = logging.getLogger(__name__)

class Status(ExportEnum):
    """
    Errors initializing export
    """
    ERROR_LOGGING = "ERROR_LOGGING"
    ERROR_GENERIC = "ERROR_GENERIC"
    ERROR_FILE_NOT_FOUND = "ERROR_FILE_NOT_FOUND"


def start():
    try:
        configure_logging()
    except Exception:
        _exit_gracefully(submission=None, status=Status.ERROR_LOGGING)

    logger.info("Starting SecureDrop Export {}".format(__version__))
    data = Archive(sys.argv[1], CONFIG_PATH)

    try:
        # Halt immediately if target file is absent
        if not os.path.exists(data.archive):
            logger.info("Archive is not found {}.".format(data.archive))
            _exit_gracefully(data, Status.ERROR_FILE_NOT_FOUND)

        # The main event. Extract archive and either print or export to disk.
        # Includes cleanup logic, which removes any temporary directories associated with
        # the archive.
        _extract_and_run(data)

    except Exception as e:
        _exit_gracefully(data, Status.ERROR_GENERIC, e.output)


def _configure_logging():
    """
    All logging related settings are set up by this function.
    """
    safe_mkdir(DEFAULT_HOME)
    safe_mkdir(DEFAULT_HOME, LOG_DIR_NAME)

    log_file = os.path.join(DEFAULT_HOME, LOG_DIR_NAME, EXPORT_LOG_FILENAME)

    # set logging format
    log_fmt = "%(asctime)s - %(name)s:%(lineno)d(%(funcName)s) " "%(levelname)s: %(message)s"
    formatter = logging.Formatter(log_fmt)

    handler = TimedRotatingFileHandler(log_file)
    handler.setFormatter(formatter)

    # For rsyslog handler
    if platform.system() != "Linux":  # pragma: no cover
        syslog_file = "/var/run/syslog"
    else:
        syslog_file = "/dev/log"

    sysloghandler = SysLogHandler(address=syslog_file)
    sysloghandler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)

    # set up primary log
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    # add the second logger
    log.addHandler(sysloghandler)


def _extract_and_run(submission: Archive):
    """
    Extract tarball and metadata and run appropriate command
    based on metadata instruction.
    """
    status = Status.ERROR_GENERIC
    stacktrace = None

    try:
        submission.extract_tarball()

        # Validates metadata and ensures requested action is supported 
        submission.archive_metadata = Metadata.create_and_validate(submission.tmpdir)

        # If we just wanted to start the VM, our work here is done
        if submission.archive_metadata.command is Command.START_VM:
            _exit_gracefully(submission)
        else:
            status = _start_service(submission, command)

    except ExportException as ex:
        status = ex.sdstatus
        stacktrace = ex.output

    except Exception as exc:
        # All exceptions are wrapped in ExportException, but we are being cautious
        logger.error("Encountered exception during export, exiting")
        status = Status.ERROR_GENERIC
        stacktrace = exc.output
        
    finally:
        _exit_gracefully(submission, status, stacktrace)


def _start_service(submission: Archive, cmd: Command) -> Status:
    """
    Start print or export routine.
    """
    if cmd in Command.printer_actions():
        service = PrintService(submission)

        if cmd is Commmand.PRINTER:
            return service.print()
        elif cmd is Commmand.PRINTER_TEST:
            return service.printer_preflight()
        elif cmd is Commmand.PRINTER_TEST:
            return service.printer_test()

    elif cmd in Command.export_actions():
        service = ExportService(submission)

        if cmd is Commmand.EXPORT:
            return service.export()
        elif cmd is Commmand.CHECK_USBS:
            return service.check_connected_devices()
        elif cmd is Commmand.CHECK_VOLUME:
            return service.checK_disk_format()


def _exit_gracefully(submission: Archive, status: Status=None, e=None):
    """
    Utility to print error messages, mostly used during debugging,
    then exits successfully despite the error. Always exits 0,
    since non-zero exit values will cause system to try alternative
    solutions for mimetype handling, which we want to avoid.
    """
    logger.info(f"Exiting with status: {status.value}")
    if e:
        logger.error("Captured exception output: {}".format(e.output))
    try:
        # If the file archive was extracted, delete before returning
        if submission and os.path.isdir(submission.tmpdir):
            shutil.rmtree(submission.tmpdir)
        # Do this after deletion to avoid giving the client two error messages in case of the
        # block above failing
        _write_status(status)
    except Exception as ex:
        logger.error("Unhandled exception: {}".format(ex))
        _write_status(Status.ERROR_GENERIC)
    finally:
        # exit with 0 return code otherwise the os will attempt to open
        # the file with another application
        sys.exit(0)


def _write_status(status: Status):
    """
    Write string to stderr.
    """
    if status:
        sys.stderr.write(status.value)
        sys.stderr.write("\n")
    else:
        logger.info("No status value supplied")

