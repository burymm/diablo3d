@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
cd /d "e:\games\diablo-1-source\vendor\the-hell-4-src"
cl /nologo /EHsc /std:c++20 /permissive /Zc:strictStrings- /Zc:__cplusplus /bigobj /DOPTIMIZE=1 /DMSVC_TOOLSET=145 /DPRJ_NAME="TH4" /DWIN32 /D_WINDOWS /DNDEBUG /I. /Isrc _offsetdump.cpp /Fe:_offsetdump.exe
echo EXITCODE=%ERRORLEVEL%
