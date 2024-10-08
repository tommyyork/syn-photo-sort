## Intro
This script will bucket photos from a given source directory into a dated tree structure in a destination directory.

This was forked from a script that used a slower exif library when invoked for each file, and now uses ExifTool/PyExiftool, which seems to have taken the metadata calculation down from about 0.22 seconds per file to ~.05s file.

This script was written to run on a Synology NAS with DiskStation on board (python 2.7, and exiftool installed). If no EXIF date and time are found, it falls back to using the file systems "last modified" date and time.  It also handles duplicates by checking for MD5 collisions if matching timestamps are found.  If there aren't duplicates and just so happen to be unique photos taken at that exact same date and time, it will add a counter on to the end of the filename (look at the example below with the `-0001`) to prevent conflicts.

The destination structure looks like he following:
```
Dest/
  2012/
    2012-01-15
        20120115-183511.jpg
        20120115-183511-0001.jpg
        20120115-193501.jpg
```

## Changes in this fork:

* Use exiftool instead of exiv2. While slightly slower, it supports a far wider range of file formats, including metadata from HEIC (raw Iphone photos) and so on.
* Slightly different directory structure, one that matches how Lightroom sets up it's chronological imports.
* It is tested and working on a DS1522+ running DSM 7.2.1-69057 Update 5. The original version worked fine as well, as exiv2 is installed by default in the DSM distribution.


## Usage
These are the program arguments:
```
usage: syn_photo_sort.py [-h] [-m] [-f] [-v] source destination type

required arguments:
  source       The source directory to read image/video files from.
  destination  The destination directory to put image/video files, renamed and
               with the proper folder structure
  type         The type of files to move. Specify one: photo, video, all

optional arguments:
  -h, --help    show this help message and exit
  -m, --move    Specify to move source files to their new location instead of
  -v, --verbose Stats on hashing and and exiftool execution.
  -f, --fuzzy   Some iPhoto libraries have aae files that include underscores + a number, potentially indicating a revision. With this arugment, make the same attempt to copy/move the sidecar file, and append the origin underscore + number.
```

The source directory is scanned recursively, for whatever kind of file you specified via the type flag of "photo" or 
"video".  The types and extensions are as follows:

 * photo: `'.JPG', '.PNG', '.THM', '.CR2', '.NEF', '.DNG', '.RAW', '.NEF', '.JPEG', .RW2', '.ARW', '.HEIC'`
 * sidecars: `'.AAE', '.XMP'`
 * video: `'.3PG', '.MOV', '.MPG', '.MPEG', '.AVI', '.3GPP', '.MP4'`

 Note: many many more formats are supported by exiftool, and might be worth testing for relevant fields. Currently, Create Date or Date Created seem sufficient for the formats I've encountered, but there are way more formats supported by exiftool that may have different metadata names that are relevant.

If you specify the `-m` or `--move` flag, it will move the source file to its intended destination and delete it from 
the source directory.  It will also clean up any existing empty folders that might exist.  It will however leave the 
root source directory.


## Setup For Synology NAS

First, you must set up Perl on your Synology NAS. Per the Perl install instructions:

> - Using your favourite browser open the DSM management page 
> and start the Package Center.
> - In Settings, add the following Package Sources:
>    
>    ```
>    Name:     Community
>    Location: https://synopackage.com/repository/spk/All
>    ```
>   
> - Still in Settings, in Channel Update, select Beta Channel.
> (https://perldoc.perl.org/perlsynology)

Be wary of using `sudo` to `make install`, potentially for this reason, the permissions were incorrect on my Perl executable, so I had to `sudo chmod 777 /volume1/@appstore/Perl/usr/local/bin/perl`.

Once you've installed Perl from the package center, you can follow the [exiftool installation instructions](https://exiftool.org/install.html).

You can setup your cron job by using DSM and visiting the "Task Scheduler".  Create a new user
`user defined script` and place all the command line calls you want to run.  Such as:
```bash
python syn_photo_sort -m /data/source /data/destination photo
```

### TODO

* Would be great to have an csv output file that reported every file copied / moved, whether it was a duplicate, etc.
* Sometimes exiftool is not closing properly, yielding `/usr/bin/python: bad interpreter: Text file busy`
* DSM 7.2 leaves @eaDir in many directories, with previews of images. Would be nice to have an option to remove the directory if it's the only thing left. Or .DS_Store.