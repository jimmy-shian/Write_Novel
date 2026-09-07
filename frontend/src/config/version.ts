/**
 * Single Source of Truth for Application Version.
 * Imported directly from root version.json.
 */
import versionData from '../../../version.json';

export const APP_VERSION: string = versionData.version;
export const APP_NAME: string = versionData.appName;
export const APP_CODENAME: string = versionData.codename;
export const APP_BUILD_DATE: string = versionData.buildDate;

export function getAppVersionInfo() {
  return {
    version: APP_VERSION,
    appName: APP_NAME,
    codename: APP_CODENAME,
    buildDate: APP_BUILD_DATE,
  };
}
