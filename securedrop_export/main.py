import logging

from securedrop_export import export
from securedrop_export.export import ExportStatus

logger = logging.getLogger(__name__)


def __main__(submission):
    submission.extract_tarball()

    try:
        submission.archive_metadata = export.Metadata(submission.tmpdir)
    except Exception:
        submission.exit_gracefully(ExportStatus.ERROR_METADATA_PARSING.value)

    if submission.archive_metadata.is_valid():
        if submission.archive_metadata.export_method == "usb-test":
            logger.info('Export archive is usb-test')
            submission.check_usb_connected(exit=True)
        elif submission.archive_metadata.export_method == "disk":
            logger.info('Export archive is disk')
            # check_usb_connected looks for the drive, sets the drive to use
            submission.check_usb_connected()
            logger.info('Unlocking volume')
            # exports all documents in the archive to luks-encrypted volume
            submission.unlock_luks_volume(submission.archive_metadata.encryption_key)
            logger.info('Mounting volume')
            submission.mount_volume()
            logger.info('Copying submission to drive')
            submission.copy_submission()
        elif submission.archive_metadata.export_method == "disk-test":
            logger.info('Export archive is disk-test')
            # check_usb_connected looks for the drive, sets the drive to use
            submission.check_usb_connected()
            submission.check_luks_volume()
        elif submission.archive_metadata.export_method == "printer":
            logger.info('Export archive is printer')
            # prints all documents in the archive
            logger.info('Searching for printer')
            printer_uri = submission.get_printer_uri()
            logger.info('Installing printer drivers')
            printer_ppd = submission.install_printer_ppd(printer_uri)
            logger.info('Setting up printer')
            submission.setup_printer(printer_uri, printer_ppd)
            logger.info('Printing files')
            submission.print_all_files()
        elif submission.archive_metadata.export_method == "printer-test":
            # Prints a test page to ensure the printer is functional
            printer_uri = submission.get_printer_uri()
            printer_ppd = submission.install_printer_ppd(printer_uri)
            submission.setup_printer(printer_uri, printer_ppd)
            submission.print_test_page()
    else:
        submission.exit_gracefully(ExportStatus.ERROR_ARCHIVE_METADATA.value)
