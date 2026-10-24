import typia from "typia";

/** How the car app reaches the Pi. The names match its `ConnectionMode`. */
export type PhoneConnectionMode = "AUTOMATIC" | "BLUETOOTH" | "ACCESS_POINT";

/** The car app's own settings, and how it reaches the Pi now. */
export interface PhoneAppState {
  mode: PhoneConnectionMode;
  /** "wifi", "bluetooth", "access_point", or "searching" while it looks. */
  connection: "wifi" | "bluetooth" | "access_point" | "searching";
  /** The Pi's address on the Wi-Fi network, while the app uses it. */
  pi_address: string | null;
  access_point_url: string;
  access_point_ssid: string;
  /** The app never hands its access point password to the page. */
  has_access_point_password: boolean;
  /** True while Android lacks a permission that the app needs. */
  missing_permissions: boolean;
  app_version: string;
  /** Android's App languages choice, such as "nl", or null for the system language. */
  language: string | null;
}

/** A change to the car app's settings. A null password keeps the saved one. */
export interface PhoneAppSettingsWrite {
  mode: PhoneConnectionMode;
  access_point_url: string;
  access_point_ssid: string;
  access_point_password: string | null;
}

/**
 * The car app's settings, as the web app inside it sees them.
 *
 * The car app (deq-tune-auto) adds `window.DeqAndroidSettings` to its web
 * view. A browser has none, so `phoneAppApi()` returns null there and the
 * settings page shows no Phone app section. After a change, and after each
 * search for the Pi, the car app fires `deq-phone-app-change` on `window`.
 */
export interface PhoneAppApi {
  read(): PhoneAppState;
  save(change: PhoneAppSettingsWrite): void;
  searchAgain(): void;
  askPermissions(): void;
  /** Sets Android's App languages choice to a language tag, such as "nl". */
  setLanguage(languageTag: string): void;
  /** Asks where to save, with Android's own save dialog. True once saved. */
  saveFile(fileName: string, text: string): Promise<boolean>;
  /** Calls `listener` on each change. Returns the function that stops it. */
  onChange(listener: () => void): () => void;
}

export const PHONE_APP_CHANGE_EVENT = "deq-phone-app-change";
/** The car app fires it after its save dialog, with `detail.saved`. */
export const PHONE_APP_FILE_SAVED_EVENT = "deq-phone-app-file-saved";

/** The shape of the car app's JavaScript interface. It passes JSON as text. */
interface AndroidSettingsInterface {
  read(): string;
  save(changeJson: string): void;
  searchAgain(): void;
  askPermissions(): void;
  setLanguage(languageTag: string): void;
  saveFile(fileName: string, text: string): void;
}

/** Wraps the car app's interface, and checks what it returns. */
export function phoneAppApi(host: Window = window): PhoneAppApi | null {
  const android = (host as Window & { DeqAndroidSettings?: AndroidSettingsInterface }).DeqAndroidSettings;
  if (android === undefined) {
    return null;
  }
  return {
    read: () => typia.assert<PhoneAppState>(JSON.parse(android.read())),
    save: (change) => android.save(JSON.stringify(typia.assert<PhoneAppSettingsWrite>(change))),
    searchAgain: () => android.searchAgain(),
    askPermissions: () => android.askPermissions(),
    setLanguage: (languageTag) => android.setLanguage(languageTag),
    saveFile: (fileName, text) =>
      new Promise((resolve) => {
        host.addEventListener(
          PHONE_APP_FILE_SAVED_EVENT,
          (savedEvent) => resolve((savedEvent as CustomEvent<{ saved: boolean }>).detail.saved),
          { once: true },
        );
        android.saveFile(fileName, text);
      }),
    onChange: (listener) => {
      host.addEventListener(PHONE_APP_CHANGE_EVENT, listener);
      return () => host.removeEventListener(PHONE_APP_CHANGE_EVENT, listener);
    },
  };
}
