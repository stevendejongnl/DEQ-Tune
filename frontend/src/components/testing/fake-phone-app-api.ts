import type { PhoneAppApi, PhoneAppSettingsWrite, PhoneAppState } from "../../api/phone-app.ts";

/** The car app's settings in memory. `report` stands for the car app's
 * change event, such as the end of a search for the Pi. */
export class FakePhoneAppApi implements PhoneAppApi {
  state: PhoneAppState;
  saved: PhoneAppSettingsWrite[] = [];
  searches = 0;
  permissionRequests = 0;
  languagesSet: string[] = [];
  savedFiles: string[] = [];
  private listeners = new Set<() => void>();

  constructor(state: Partial<PhoneAppState> = {}) {
    this.state = {
      mode: "AUTOMATIC",
      connection: "wifi",
      pi_address: "192.168.1.20",
      access_point_url: "http://192.168.4.1:8420",
      access_point_ssid: "deq-tune",
      has_access_point_password: false,
      missing_permissions: false,
      app_version: "0.1.0",
      language: null,
      ...state,
    };
  }

  read(): PhoneAppState {
    return this.state;
  }

  save(change: PhoneAppSettingsWrite): void {
    this.saved.push(change);
    this.state = {
      ...this.state,
      mode: change.mode,
      access_point_url: change.access_point_url,
      access_point_ssid: change.access_point_ssid,
      has_access_point_password: this.state.has_access_point_password || change.access_point_password !== null,
    };
  }

  searchAgain(): void {
    this.searches += 1;
  }

  askPermissions(): void {
    this.permissionRequests += 1;
  }

  async saveFile(fileName: string): Promise<boolean> {
    this.savedFiles.push(fileName);
    return true;
  }

  setLanguage(languageTag: string): void {
    this.languagesSet.push(languageTag);
    this.state = { ...this.state, language: languageTag };
  }

  onChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  report(state: Partial<PhoneAppState>): void {
    this.state = { ...this.state, ...state };
    this.listeners.forEach((listener) => listener());
  }
}
