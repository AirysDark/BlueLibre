!define APPNAME "AirPodsDesktop"
!define VERSION "0.4.0"
!define APPDIR "$PROGRAMFILES64\${APPNAME}"

OutFile "AirPodsDesktop-${VERSION}-win64-setup.exe"
InstallDir "${APPDIR}"
RequestExecutionLevel admin
Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\build\out\bin\*.*"
  CreateShortCut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\AirPodsDesktop.exe"
SectionEnd