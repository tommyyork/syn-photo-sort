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

######################## Functions #########################

#TODO: junk mobile photos: FB_*,  *-ANIMATION.gif, *-COLLAGE*

def removeEmptyFolders(path, removeRoot=True):
  'Function to remove empty folders'
  if not os.path.isdir(path):
    return

  # remove empty subfolders
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

def copyOrHash(et, duplicate, f, filename, problems, fHash, thisDestDir, destFileName, suffix, fExt, errorDir, move):
    global hash_timing
    global hash_invokes
            
    print(f"Attempting to {'move' if move else 'copy'} {f}...")
    
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
          print('Bailing, duplicate...')
          skipCopy = True
          break

        duplicate = thisDestDir + '/%s-%04d.' % (destFileName, suffix) + fExt
        suffix += 1

      # Different hash or not a duplicate, persist at the destination!
      if(skipCopy == False):
        if(move == False):
          shutil.copy2(f, duplicate)
          print(f"to: {duplicate}")
        else:
          shutil.move(f, duplicate)
          print(f"to: {duplicate}")
          # print here
      else:
        if(move == True):
          os.remove(f)
    except Exception as e:
      if not os.path.exists(errorDir):
        os.makedirs(errorDir)

      if(move == False):
        shutil.copy2(f, errorDir + filename)
        print(f"to: {errorDir + duplicate}")
        # print here
      else:
        shutil.move(f, errorDir + filename)
        print(f"to: {errorDir + duplicate}")
        # print here

      print(str(e))
      print(traceback.extract_stack())
      problems.append(f)

      et.terminate()
      sys.exit("Execution stopped.")

def getUnderscoreOfSidecar(sidecar):
  """ sidecar: full path to sidecar """
  print(f"testing sidecar {sidecar}")
  sidecar = os.path.split(sidecar)[1]
  sidecar = os.path.splitext(sidecar)[0]
  underscoredNumber = re.search(r'(_[0-9]$)', sidecar).group()
  return "" if not len(underscoredNumber) else underscoredNumber


def handleFileMove(et, f, filename, fFmtName, sidecarExtensions, args, problems, move, sourceDir, destDir, errorDir):
  """
  f: full filename, including directory: test_folders/test/99774A38-D2F3-45C2-B54F-018E7BB854D8_3.mov
  filename: 99774A38-D2F3-45C2-B54F-018E7BB854D8_3.mov
  fFmtName: %Y%m%d-%H%M%S
  sourceDir: test_folders/test
  """
  
  print("")
  print("Processing: %s..." % f)

  fExt = filenameExtension(f)

  sidecar = str()
  sidecarExt = str()
  # Check for exact sidecar match
  for sidecarExtension in sidecarExtensions:
    sidecarExtension = sidecarExtension.lower()
    potentialSidecar = os.path.join(sourceDir, os.path.splitext(filename)[0] + sidecarExtension)
    if os.path.exists(potentialSidecar):
      print(f"Found metadata sidecar, will copy/move as well: {potentialSidecar}")
      sidecar = potentialSidecar
      sidecarExt = sidecarExtension
      break
    if (args.fuzzy and len(sidecar) == 0):
      for sidecarExtension in sidecarExtensions:
        sidecarExtension = sidecarExtension.lower()
        filenameWithoutExt = os.path.splitext(filename)[0]
        filenameWithoutExtOrUnderscore = re.sub(r'(_[0-9]$)', '', filenameWithoutExt)
        if filenameWithoutExt is not filenameWithoutExtOrUnderscore:
          filenameUnderscore = re.findall(r'(_[0-9]$)', filenameWithoutExt)[0]
        else:
          filenameUnderscore = ""
        globString = os.path.join(sourceDir,filenameWithoutExtOrUnderscore) + '*' + sidecarExtension + filenameUnderscore
        for n in glob.glob(globString):
          if os.path.exists(n):
            sidecar = n
            sidecarFilename = os.path.split(sidecar)[1]
            sidecarExt = sidecarExtension
            print(f"Found metadata sidecar fuzzily matched, will copy/move as well: {n}")
            break
    
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
    
    destFileName = pDate.strftime(fFmtName)
    if (len(sidecar) > 0):
      destSidecarFilename = destFileName + os.path.splitext(sidecar)[1]
    thisDestDir = destDir + '/%04d/%04d-%02d-%02d' % (yr, yr, mo, day)

    if not os.path.exists(thisDestDir):
      os.makedirs(thisDestDir)

    duplicate = thisDestDir + '/%s.' % (destFileName) + fExt
    if (len(sidecar) > 1):
      duplicateSidecar = thisDestDir + '/%s' % (destFileName) + getUnderscoreOfSidecar(sidecar) + sidecarExt 

    copyOrHash(et, duplicate, f, filename, problems, fHash, thisDestDir, destFileName, suffix, fExt, errorDir, move)
    if (len(sidecar) > 0):
      copyOrHash(et, duplicateSidecar, sidecar, sidecarFilename, problems, fHash, thisDestDir, destSidecarFilename, suffix, sidecarExt, errorDir, move)

  except Exception as e:
    print(traceback.extract_stack())
    print(str(e))
   

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
    photoExtensions = ['.JPG', '.PNG', '.THM', '.CR2', '.NEF', '.DNG', '.RAW', '.NEF', '.JPEG', '.RW2', '.ARW', '.HEIC', '.PSD', '.TIF']
    # sidecarExtensions we care about
    sidecarExtensions = ['.AAE', '.XMP']
    # TODO: many many more extensions to test and see if they yield the correct create dates, both for photo and video.
    videoExtensions = ['.3PG', '.MOV', '.MPG', '.MPEG', '.AVI', '.3GPP', '.MP4', '.ASF']
    
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
      if(move == True):
        removeEmptyFolders(sourceDir, False)

    # Report the problem files, if any.
    if (len(problems) > 0):
      print("\nProblem files:")
      print("\n".join(problems))
      print("These can be found in: %s" % errorDir)
    else :
      print("\nSuccess!")

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
  
