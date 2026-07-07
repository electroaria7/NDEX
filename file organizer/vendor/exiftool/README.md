Place the extracted Windows ExifTool files in this folder before building the distributable package.

Expected minimum structure:

```text
vendor/exiftool/exiftool.exe
vendor/exiftool/exiftool_files/...
```

The packaged DSB app will call this binary internally for CR3 metadata extraction.

The official ExifTool documentation notes that `exiftool.exe` must stay together with the `exiftool_files` folder.
