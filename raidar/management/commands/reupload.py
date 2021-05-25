from django.core.management.base import BaseCommand, CommandError
from raidar.models import *
from time import time
import os
import os.path
import logging
import re

logger = logging.getLogger(__name__)


# Command to reupload logs that threw errors
def reupload(*args, **options):
    logger.info('Reuploading...')
    upload_path = os.path.relpath("uploads")
    error_path = os.path.join(upload_path, "errors")

    verbose = True if options['verbosity'] >= 2 else False

    # if no files specified, get all error logs from error folder
    if options['files'] is not None:
        files = options['files']
    else:
        files = os.listdir(error_path)

    # create set of unique zevtc logs
    files = set(re.sub(r'\.error', '', file) for file in files)

    for filename in files:
        # append ending if necessary
        if not filename.endswith('.zevtc'):
            filename = filename + ".zevtc"

        filepath = os.path.join(error_path, filename)

        # Skip folders
        if not os.path.isfile(filepath):
            logger.error('Path is not a file: ' + filepath)
            continue

        try:
            with open(filepath + '.error', 'r') as f:
                logger.info('Reading ' + filename)
                # extract original name and user from matching error log
                match = re.match(r"(.*) \((.*?)\)", f.readline().rstrip())
                orig_name = match.group(1)
                username = match.group(2)
        except FileNotFoundError:
            logger.error('File not found: ' + filepath)
            continue

        # reupload the log
        user = User.objects.get(username=username)
        upload_time = os.path.getmtime(filepath)
        upload, _ = Upload.objects.update_or_create(
            filename=orig_name, uploaded_by=user,
            defaults={"uploaded_at": upload_time})

        # cleanup error files
        new_diskname = upload.diskname()
        os.makedirs(os.path.dirname(new_diskname), exist_ok=True)
        os.rename(filepath, new_diskname)
        os.remove(filepath + '.error')


class Command(BaseCommand):
    help = 'Reupload EVTC files'

    def add_arguments(self, parser):
        parser.add_argument('--files',
                            nargs='+',
                            help='EVTC files to reupload',
                            required=False)

    def handle(self, *args, **options):
        if options['verbosity'] == 2:
            logger.setLevel(logging.ERROR)
        elif options['verbosity'] == 3:
            logger.setLevel(logging.INFO)
        start = time()
        logger.info('Starting', start)
        reupload(*args, **options)
        end = time()

        if options['verbosity'] >= 3:
            print()
            print("Completed in %ss" % (end - start))
