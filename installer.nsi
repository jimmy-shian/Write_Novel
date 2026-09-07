; NSIS Installation Script for AI Novel Factory
!define PRODUCT_NAME "AI Novel Factory"
!define PRODUCT_VERSION "4.0.0"
!define PRODUCT_PUBLISHER "AI Novel Factory Team"
!define PRODUCT_WEB_SITE "https://github.com/jimmy-shian/Write_Novel"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\AI_Novel_Factory.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

SetCompressor /SOLID lzma
Unicode true

!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "frontend\public\favicon.ico"
!define MUI_UNICON "frontend\public\favicon.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\AI_Novel_Factory.exe"
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "TradChinese"
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist-packages\AI_Novel_Factory_v${PRODUCT_VERSION}_Setup.exe"
InstallDir "$PROGRAMFILES64\AI Novel Factory"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show

Section "MainSection" SEC01
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer
  File /r "dist-packages\AI_Novel_Factory\*.*"

  ; Shortcuts
  CreateDirectory "$SMPROGRAMS\AI Novel Factory"
  CreateShortcut "$SMPROGRAMS\AI Novel Factory\AI Novel Factory.lnk" "$INSTDIR\AI_Novel_Factory.exe"
  CreateShortcut "$DESKTOP\AI Novel Factory.lnk" "$INSTDIR\AI_Novel_Factory.exe"
  CreateShortcut "$SMPROGRAMS\AI Novel Factory\Uninstall.lnk" "$INSTDIR\uninst.exe"
SectionEnd

Section -Post
  WriteUninstaller "$INSTDIR\uninst.exe"
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\AI_Novel_Factory.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\AI_Novel_Factory.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

Function un.onUninstSuccess
  HideWindow
  MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) 已成功自您的電腦中移除。"
FunctionEnd

Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "確定要徹底移除 $(^Name) 及其所有組件？" IDYES +2
  Abort
FunctionEnd

Section Uninstall
  Delete "$DESKTOP\AI Novel Factory.lnk"
  Delete "$SMPROGRAMS\AI Novel Factory\*.*"
  RMDir "$SMPROGRAMS\AI Novel Factory"

  RMDir /r "$INSTDIR"

  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
  SetAutoClose true
SectionEnd
