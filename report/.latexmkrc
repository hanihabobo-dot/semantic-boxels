$pdf_mode = 1;
$pdflatex = 'lualatex --interaction=nonstopmode %O %S';
$clean_ext = 'loa lol tdo';

# Report only: the fonts are the thesis's (../thesis/fonts/, never copied). Put that folder
# on kpathsea's font search path; the trailing separator appends the default search path.
$ENV{'TTFONTS'} = '../thesis/fonts//' . (($^O eq 'MSWin32') ? ';' : ':');