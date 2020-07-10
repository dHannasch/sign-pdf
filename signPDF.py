#!/usr/bin/env python2
"""
Right now it uses gimp for the actual drawing part,
which is annoying because gimp refuses to save a .ppm file back as the same .ppm file;
gimp will only do that if you File->Export
and confirm to overwrite the original /tmp/pdftoppm_temp.ppm.
And then gimp still nags you when you close it that you haven't *really* saved it as a proper XCF format.
It does work, though.

There is a tool xcf2pnm http://manpages.ubuntu.com/manpages/trusty/man1/xcf2pnm.1.html
but not a tool pnm2xcf.

pinta will not open ppm files.
"""

import argparse
import subprocess,sys
import os.path
import re

def get_pdftoppm_version():
  pdftoppm_version = subprocess.check_output(['pdftoppm', '-v'], stderr=subprocess.STDOUT, encoding='ASCII')
  matchObj = re.match('pdftoppm version (\d+)\.(\d+)\.(\d+)', pdftoppm_version)
  if matchObj is None:
    raise ValueError(pdftoppm_version)
  version = tuple(int(matchObj.group(i) ) for i in range(1, 4) )
  return version


parser = argparse.ArgumentParser(description='sign a page of a PDF')
parser.add_argument('PDFfilename', metavar='PDFfilename',
                    help='name of the PDF file')
parser.add_argument('--page', '-n',
                    # nargs='+' would make list
                    type=int, default=1,
                    help='page of the PDF file')
parser.add_argument('--delete',
                    type=int, default=None,
                    help='page to delete')
parser.add_argument('--editor', '-e',
                    default='gimp',
                    help='image editor to call on the temporary image file; gimp refuses to save as .ppm, requires you to File->Export instead, is there a better way?')
args = parser.parse_args()
tempimgformat = 'png' # ppm does not have layers
tempimgfileprefix = '/tmp/pdftoppm_temp'
singlepagePDFfilename = tempimgfileprefix + '.pdf'
finalFileName = os.path.splitext(args.PDFfilename)[0] + '.signed.pdf'

"""
http://netpbm.sourceforge.net/doc/ppm.html
1. A "magic number" for identifying the file type. A ppm image's magic number is the two characters "P6".
3. A width, formatted as ASCII characters in decimal.
5. A height, again in ASCII decimal.
7. The maximum color value (Maxval), again in ASCII decimal.
There is actually another version of the PPM format that is fairly rare: "plain" PPM format. The format above, which generally considered the normal one, is known as the "raw" PPM format.
pdftoppm documentation does not seem to specify, but it uses raw:
/tmp$ xxd pdftoppm_temp.ppm | head
0000000: 5036 0a31 3234 3020 3137 3534 0a32 3535  P6.1240 1754.255
/tmp$ head --bytes=17 pdftoppm_temp.ppm
P6
1240 1754
255

If you look at PyPDF2/pdf.py, scaleTo() refers to mediaBox.

https://github.com/mstamy2/PyPDF2
might need to make scaleTo support subclasses of decimal.Decimal since that's what mediaBox has
"""

"""
We eventually want to use Pillow to automate the process of creating a new layer, opening all layers together for drawing, then deleting the original layer. In the meantime, this can be done manually using gimp.
Open Windows -> Dockable Dialogs -> Layers with Ctrl+L.
Create a new layer, do whatever you need to, then delete the original layer by clicking the red circle or right-clicking the layer in the list.
"""

import PyPDF2
# http://linux.die.net/man/1/pdftoppm
# https://poppler.freedesktop.org/releases.html
pdftoppmArgs = ['-f', str(args.page),
                '-freetype', 'yes']
if get_pdftoppm_version() < (0,17,0):
  pdftoppmArgs.extend(['-l', str(args.page)])
else:
  pdftoppmArgs.append('-singlefile')
if tempimgformat != 'ppm': pdftoppmArgs.append('-' + tempimgformat)
print('pdftoppm options:', pdftoppmArgs)
pdftoppmCall = ['pdftoppm'] + pdftoppmArgs + [args.PDFfilename, tempimgfileprefix]
print('pdftoppmCall =', pdftoppmCall)
if get_pdftoppm_version() < (0,14,2):
  tempimgfilename = tempimgfileprefix + '-' + str(args.page) + '.' + tempimgformat
else:
  tempimgfilename = tempimgfileprefix + '.' + tempimgformat
subprocess.check_call(pdftoppmCall,
                stdout=sys.stdout, stderr=sys.stderr)
subprocess.check_call([args.editor, tempimgfilename], stdout=sys.stdout, stderr=sys.stderr)
try:
  subprocess.check_call(['convert', tempimgfilename, singlepagePDFfilename], stdout=sys.stdout, stderr=sys.stderr)
except subprocess.CalledProcessError:
  raise Exception('''By default, ImageMagick convert will throw an error:
convert: not authorized `/tmp/pdftoppm_temp.pdf' @ error/constitute.c/WriteImage/1028.
To fix this, sudo nano /etc/ImageMagick-6/policy.xml and change
<policy domain="coder" rights="none" pattern="PDF" />
to
<policy domain="coder" rights="write" pattern="PDF" />''')
# Somehow, the round-trip is making the image larger (in dimension, not just file size), so the final PDF has one page larger than the others. This isn't a question of moving to a larger set size; if you re-run on the same page, it will get even bigger.
assert os.path.exists(singlepagePDFfilename)
signedPage = PyPDF2.PdfFileReader(singlepagePDFfilename)
assert signedPage.getNumPages() == 1
originalPDF = PyPDF2.PdfFileReader(args.PDFfilename)
output = PyPDF2.PdfFileWriter()
for index,page in enumerate(originalPDF.pages):
    if index != args.page - 1:
        if args.delete is None or index != args.delete - 1:
            output.addPage(page)
    else:
        assert index + 1 == args.page
        originalSize = page.mediaBox # also artBox, bleedBox, cropBox, trimBox
        newPage = signedPage.getPage(0)
        newSize = newPage.mediaBox
        if originalSize != newSize:
            print('size changed from', originalSize, 'to', newSize, 'fixing...')
            newPage.scaleTo(float(originalSize[2]), float(originalSize[3]))
        page.mergePage(newPage)
        # PIL also does this https://stackoverflow.com/questions/5324647/how-to-merge-a-transparent-png-image-with-another-image-using-pil
        # but PIL probably cannot handle text
        output.addPage(page)
output.write(open(finalFileName, 'wb') )
