#!/usr/bin/python

import sys
import fnmatch
import os
import platform
import shutil
import hashlib
import traceback
import os.path
import datetime
import argparse
import glob
import re
import time
from datetime import datetime
from exiftool import ExifTool

# Set up timing variables
global exiftool_timing
exiftool_timing = float(0)
global exiftool_invokes
exiftool_invokes = int(0)
global hash_timing
hash_timing = float(0)
global hash_invokes
hash_invokes = int(0)

global processed
processed = int(0)

######################## Functions #########################

#TODO: junk mobile photos: FB_*,  *-ANIMATION.gif, *-COLLAGE*

def removeEmptyFolders(path, removeRoot=True):
  'Function to remove empty folders'
  directoriesToDelete = ["@eaDir"]
  filesToDelete = [".DS_Store"]

  if not os.path.isdir(path):
    return

  # remove @eaDir and .DS_Store
  files = os.listdir(path)
  for f in files:
    if f in directoriesToDelete:
      fullpath = os.path.join(path, f)
      # Remove Synology preview folders somewhat dangerously.
      shutil.rmtree(fullpath)
    if f in filesToDelete:
      fullpath= os.path.join(path, f)
      if os.path.exists(fullpath):
        os.remove(fullpath)
    
  files = os.listdir(path)
  if len(files):
    for f in files:
      fullpath = os.path.join(path, f)
      if os.path.isdir(fullpath):
        removeEmptyFolders(fullpath)

  # if folder empty, delete it
  files = os.listdir(path)
  if len(files) == 0 and removeRoot:
    os.rmdir(path)
  elif len(files) > 0 and removeRoot:
    print(f"Directory {path} not empty, so not deleting.")

def checkForExiftool(et):
  "Ensures we have exiftool installed" 
  try:
    et.__init__(common_args=["-n"])
    et.run()
    et.execute("-ver")
  except et.ExifToolNotRunning as e:
    print("Unable to get exiftool running.")
    print(str(e))
  except et.ExifToolVersionError as e:
    print ("Please upgrade your exiftool version.")
    print(str(e))
  except e:
    print(str(e))
  

def outputFromExiftool(et, f):
  "Output from exiftool."
  output = None 

  global exiftool_timing
  global exiftool_invokes 

  try:
    t1 = time.perf_counter(), time.process_time()
    output = et.execute('-createDate',  f)
    t2 = time.perf_counter(), time.process_time()
    exiftool_timing = exiftool_timing + t2[0] - t1[0]
    exiftool_invokes = exiftool_invokes + 1

    if ("Create Date" not in output):
      t1 = time.perf_counter(), time.process_time()
      output = et.execute('-dateCreated', f)
      t2 = time.perf_counter(), time.process_time()
      exiftool_timing = exiftool_timing + t2[0] - t1[0]
      exiftool_invokes = exiftool_invokes + 1
    return output
    # TODO: There's yet another exiftool flag - exiftool -time:all -a FILE - that can give you more records, but these mostly 
    # seem similar to just file modification dates. Might be worth replacing the filesystem checks with this though.
  
  # this might be broken:
  except Exception as e:
    print(str(e))
    et.terminate()
    return '' 

def photoDate(et, f):
  "Return the date/time on which the given photo was taken. Uses exiftool, on Synology by default"
  output = outputFromExiftool(et, f)
  if(not output):
    # No Exif, use modified date/time
    return creationDate(f) 
  try:
    # There's a cleaner way to do this in exiftool, consider it a TODO.
    rawDate = output.split(':',1)[1].lstrip().rstrip()
    parsedDate = datetime.strptime(rawDate, "%Y:%m:%d %H:%M:%S")
    return parsedDate
  except ValueError as e:
    print(str(e))
    print('Error processing metadata date information from the file, will use filesystem creation date.')
    # Couldn't parse the field, probably bad or missing exif data
    return creationDate(f)

def creationDate(f):
  "Gets a DateTime from a files creation date via the file system"
  if platform.system() == 'Windows':
    return datetime.fromtimestamp(os.path.getctime(f))
  else:
    stat = os.stat(f)
    try:
      return datetime.fromtimestamp(stat.st_birthtime)
    except AttributeError:
      # We're probably on Linux. No easy way to get creation dates here,
      # so we'll settle for when its content was last modified.
      return datetime.fromtimestamp(stat.st_mtime)

def filenameExtension(f):
  "Return the file extension normalized to lowercase."
  return os.path.splitext(f)[1][1:].strip().lower()

def copyOrHash(et, duplicate, f, filename, problems, fHash, thisDestDir, destFileName, suffix, fExt, errorDir, move, args):
    global hash_timing
    global hash_invokes
            
    if (args.verbose): print(f"Attempting to {'move' if move else 'copy'} {f}...")
    
    try:
      skipCopy = False

      while os.path.exists(duplicate):
        skipCopy = False

        # We found a duplicate at the destination, get the incoming hash
        if(fHash is None):
          t1 = time.perf_counter(), time.process_time()
          fHash = hashlib.md5(open(f, 'rb').read()).hexdigest()
          t2 = time.perf_counter(), time.process_time()
          hash_timing = hash_timing + t2[0] - t1[0]
          hash_invokes = hash_invokes + 1

        # Get the already existing files hash
        t1 = time.perf_counter(), time.process_time()
        destHash = hashlib.md5(open(duplicate, 'rb').read()).hexdigest()
        t2 = time.perf_counter(), time.process_time()
        hash_timing = hash_timing + t2[0] - t1[0]
        hash_invokes = hash_invokes + 1

        # If it's a match, bail and don't save this incoming file.
        if(fHash == destHash):
          if (args.verbose): print('Bailing, duplicate...')
          skipCopy = True
          break

        duplicate = thisDestDir + '/%s-%04d.' % (destFileName, suffix) + fExt
        suffix += 1

      # Different hash or not a duplicate, persist at the destination!
      if(skipCopy == False):
        if(move == False):
          shutil.copy2(f, duplicate)
          if (args.verbose): print(f"to: {duplicate}")
        else:
          shutil.move(f, duplicate)
          if (args.verbose): print(f"to: {duplicate}")
      else:
        if(move == True):
          os.remove(f)
    except Exception as e:
      if not os.path.exists(errorDir):
        os.makedirs(errorDir)

      if(move == False):
        shutil.copy2(f, errorDir + filename)
        if (args.verbose): print(f"to: {errorDir + duplicate}")
        # print here
      else:
        shutil.move(f, errorDir + filename)
        if (args.verbose): print(f"to: {errorDir + duplicate}")
        # print here

      print(str(e))
      print(traceback.format_exc())
      problems.append(f)

      et.terminate()
      sys.exit("Execution stopped.")

def getUnderscoreOfSidecar(sidecar):
  """ sidecar: full path to sidecar """
  sidecar = os.path.split(sidecar)[1]
  sidecarWithoutExt = os.path.splitext(sidecar)[0]
  match = re.search(r'(_[0-9]$)', sidecarWithoutExt)
  return "" if match is None else match.group()

def sidecarIsRelevant(et, sidecar, f):
  # while .xmp files have a raw file name pointing to the raw image,
  # .aae files do not, so this is not really relevant. We do not want
  # to copy an .xmp for a .jpg for which it is not relevant.
  sExt = os.path.splitext(sidecar)[1]
  if sExt == ".aae" or sExt == ".AAE": 
    return True
  else:
    exiftoolOutput = et.execute("-RawFileName", sidecar)
    if (exiftoolOutput):
      rawFileName = exiftoolOutput.split(":")[1].strip().rstrip("")
      imageFilename = os.path.split(f)[1]
      return rawFileName == imageFilename


def findRelevantSidecar(et, args, f, sidecarExtensions):
  sidecar = str()
  # Check for exact sidecar match
  for ext in [".xmp"]:
    ext = ext.lower()
    potentialExactSidecars = []
    potentialExactSidecars.append(os.path.join(os.path.splitext(f)[0] + ext))
    potentialExactSidecars.append(f + ext) # e.g. "IMG_3323_CR2_shotwell.jpg.xmp"
    for potentialExactSidecar in potentialExactSidecars:
      if os.path.exists(potentialExactSidecar):
        # if (args.verbose): print(f"Found metadata sidecar, will copy/move as well: {potentialExactSidecar}")
        if (sidecarIsRelevant(et, potentialExactSidecar, f)):
          sidecar = potentialExactSidecar
          return sidecar
  for ext in [".aae"]:
    if (args.fuzzy and len(sidecar) == 0):
      for ext in sidecarExtensions:
        ext = ext.lower()
        # get full path, without extension
        fileWithoutExt = os.path.splitext(f)[0]
        # split off whatever _# at the end
        fileWithoutExtOrUnderscore = re.sub(r'(_[0-9]$)', '', fileWithoutExt)
        globString = os.path.join(fileWithoutExtOrUnderscore) + '*' + ext
        for n in glob.glob(globString):
          if os.path.exists(n):
            sidecar = n
            # if (args.verbose): print(f"Found metadata sidecar fuzzily matched, will copy/move as well: {n}")
            return sidecar
  return None


def handleFileMove(et, f, filename, fFmtName, sidecarExtensions, args, problems, move, sourceDir, destDir, errorDir):
  """
  f: full filename, including directory: test_folders/test/99774A38-D2F3-45C2-B54F-018E7BB854D8_3.mov
  filename: 99774A38-D2F3-45C2-B54F-018E7BB854D8_3.mov
  fFmtName: %Y%m%d-%H%M%S
  sourceDir: test_folders/test
  """
  
  if (args.verbose): print("")
  print("Processing: %s..." % f)
  global processed
  processed += 1

  fExt = filenameExtension(f)
  if fExt in ["cr2", "dng"]:
    fExt = fExt.upper()

  sidecar = findRelevantSidecar(et, args, f, sidecarExtensions)

  # Copy photos/videos into year and month subfolders. Name the copies according to
  # their timestamps. If more than one photo/video has the same timestamp, add
  # suffixes 0001, 0002, 0003, etc. to the names. 

  suffix = 1
  try:
    pDate = photoDate(et, f)
    yr = pDate.year
    mo = pDate.month
    day = pDate.day
    fHash = None
    
    # If we have a matching sidecar, use that sidecar for the filename instead.
    destFileName = None
    if sidecar is not None and os.path.splitext(sidecar)[1] == ".xmp":
        rawFileName = et.execute("-RawFileName", sidecar).split(":")[1].strip().rstrip("")
        # for some reason in this function extensions now do not have periods in front of them.
        rawExtension = os.path.splitext(rawFileName)[1]
        fExt = rawExtension.lstrip(".")
        if (rawExtension == fExt):
          destFileName = os.path.splitext(rawFileName)[0]
    # either no sidecar, or the sidecar was for a different file (likely a CR2, and not a jpg)
    if not destFileName: destFileName = pDate.strftime(fFmtName)

    thisDestDir = destDir + '/%04d/%04d-%02d-%02d' % (yr, yr, mo, day)

    if not os.path.exists(thisDestDir):
      os.makedirs(thisDestDir)

    duplicate = thisDestDir + '/%s.' % (destFileName) + fExt
    copyOrHash(et, duplicate, f, filename, problems, fHash, thisDestDir, destFileName, suffix, fExt, errorDir, move, args)

    if (sidecar is not None):
      sidecarFilename = os.path.split(sidecar)[1]
      sExt = os.path.splitext(sidecar)[1]
      if (sExt == ".aae"):
        destSidecarFilename = destFileName + getUnderscoreOfSidecar(sidecar)
      else:
        destSidecarFilename = destFileName
      
      duplicateSidecar = thisDestDir + '/%s' % (destSidecarFilename)
      copyOrHash(et, duplicateSidecar, sidecar, sidecarFilename, problems, fHash, thisDestDir, destSidecarFilename, suffix, sExt, errorDir, move, args)

  except Exception as e:
    print(str(e))
    print(traceback.format_exc())
    et.terminate()
    sys.exit()
   

###################### Main program ########################

def main(argv):

  # Validate required packages...
  with ExifTool() as et:
    checkForExiftool(et)

    parser = argparse.ArgumentParser(prog='syn_photo_sort', 
                                    description='Application designed to sort photos into a directory tree based on creation date derived from metadata.')
    optional = parser._action_groups.pop() # Edited this line
    required = parser.add_argument_group('required arguments')
    required.add_argument('source', type=str, help='The source directory to read image/video files from.')
    required.add_argument('destination', type=str, help='The destination directory to put image/video files, renamed and with the proper folder structure')
    required.add_argument('type', type=str, help='The type of files to move. photo, video, all (for all photo and video files)')
    optional.add_argument('-m', '--move', action='store_true', help='Specify to move source files to their new location instead of copying.')
    optional.add_argument('-v', '--verbose', action='store_true', help="Show performance information for hashing and exiftool invocation.")
    optional.add_argument('-f', '--fuzzy', action='store_true', help="Drop underscores at the end of iPhone files and AAE files to find the best matching AAE sidecar file to copy/move.")
    # add ignore errors here
    parser._action_groups.append(optional) # added this line
    args = parser.parse_args()

    # Where the photos are and where they're going.
    sourceDir = args.source
    # Remove trailing slash from the destination directory if present.
    destDir = args.destination.rstrip('/')
    scanType = args.type.upper()
    if(scanType != 'PHOTO' and scanType != 'VIDEO' and scanType != "ALL"):
      print("Incorrect type specified! Must be either 'photo' or 'video' or 'all'")
      sys.exit(1)
    
    errorDir = destDir + '/Unsorted/'
    move = args.move

    # Validate these directories exist...
    if not os.path.exists(sourceDir):
      print('Source Directory does not exist!')
      sys.exit(1)
    if not os.path.exists(destDir):
      # os.makedirs(destDir)
      print('Destination Directory does not exist!')
      sys.exit(1)

    # The format for the new file names.
    filenameFmt = "%Y%m%d-%H%M%S"

    # File Extensions we care about
    photoExtensions = ['.JPG', '.PNG', '.THM', '.CR2', '.NEF', '.DNG', '.RAW', '.NEF', '.JPEG', '.RW2',
                       '.ARW', '.HEIC', '.PSD', '.TIF', '.TIFF', '.BMP']
    # sidecarExtensions we care about
    sidecarExtensions = ['.AAE', '.XMP']
    # TODO: many many more extensions to test and see if they yield the correct create dates, both for photo and video.
    videoExtensions = ['.3PG', '.MOV', '.MPG', '.MPEG', '.MTS', '.AVI', '.3GPP', '.MP4', '.ASF']
    
    scanExtensions = photoExtensions
    if(scanType == 'VIDEO'):
      scanExtensions = videoExtensions
    elif (scanType == "ALL"):
      scanExtensions = videoExtensions + photoExtensions

    # The problem files.
    problems = []

    
    for extension in scanExtensions:
      for root, dirnames, filenames in os.walk(sourceDir):
        for filename in filenames:
          if filename.upper().endswith(extension):
            f = os.path.join(root, filename)
            handleFileMove(et, f, filename, filenameFmt, sidecarExtensions, args, problems, move, sourceDir, destDir, errorDir)
    for root, dirnames, filenames in os.walk(sourceDir):
      if(move == True):
        removeEmptyFolders(sourceDir, False)

    # Report the problem files, if any.
    if (len(problems) > 0):
      print("\nProblem files:")
      print("\n".join(problems))
      print("These can be found in: %s" % errorDir)
    else :
      print("\nSuccess!")
      print(f"Processed {processed} files.")

    if args.verbose:
      global exiftool_invokes
      global exiftool_timing
      global hash_invokes
      global hash_timing
      print("Performance stats (real time):")
      if exiftool_invokes > 0:
        print(f"Exiftool invocations: {exiftool_timing / exiftool_invokes:.2f} seconds per item")
      if hash_invokes > 0:
        print(f"Hashing: {hash_timing / hash_invokes:.4f} seconds per item")
    
    et.terminate()

######################## Startup ###########################

if __name__ == "__main__":
   main(sys.argv[1:])
  
