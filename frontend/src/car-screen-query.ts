/** The car app loads the page with `?screen=car` on the car screen
 * (`CarScreenActivity` in deq-tune-auto). The phone and a browser load it
 * without that query. */
export function isCarScreenQuery(search: string): boolean {
  return new URLSearchParams(search).get("screen") === "car";
}

export function pageIsOnCarScreen(): boolean {
  return typeof window !== "undefined" && isCarScreenQuery(window.location.search);
}
