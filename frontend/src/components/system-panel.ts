import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { BridgeSystemApi } from "../api/client.ts";
import type { BridgeSystemDto, NetworkInterfaceDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { readPageFreshness, type PageFreshness } from "../page-freshness.ts";
import { formatBytes, formatDuration, usedPercent } from "../system-format.ts";
import type { CancelFunction, ScheduleFunction } from "./device-status.ts";
import { systemPanelStyles } from "./system-panel.styles.ts";

/** How often the panel reads the statistics again while it is on the page,
 * in milliseconds. */
export const REFRESH_WHILE_OPEN_MS = 2000;

const UNKNOWN = "–";

type Row = [label: string, value: string];

function known<T>(value: T | null, write: (known: T) => string): string {
  return value === null ? UNKNOWN : write(value);
}

/** The text of one interface's line: its addresses, its traffic and its signal. */
function interfaceDetails(networkInterface: NetworkInterfaceDto): string {
  const parts = [...networkInterface.addresses];
  if (networkInterface.received_bytes !== null && networkInterface.sent_bytes !== null) {
    parts.push(`rx ${formatBytes(networkInterface.received_bytes)} · tx ${formatBytes(networkInterface.sent_bytes)}`);
  }
  if (networkInterface.signal_dbm !== null) {
    parts.push(`${networkInterface.signal_dbm} dBm`);
  }
  if (networkInterface.mac_address !== null) {
    parts.push(networkInterface.mac_address);
  }
  return parts.join("\n");
}

/**
 * Shows the DEQ unit's firmware, the Pi's machine statistics, and where
 * this page came from.
 *
 * It is the System section of the settings page. A click on the status
 * pill opens that section. While the panel is on the page, it reads
 * `/api/bridge/system` again every `REFRESH_WHILE_OPEN_MS`. It depends on
 * a `BridgeSystemApi`, on a way to schedule the next read, and on a
 * reload function. A test passes its own of each.
 */
@customElement("system-panel")
export class SystemPanel extends LitElement {
  static override styles = systemPanelStyles;

  @property({ attribute: false }) api: BridgeSystemApi | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) pageBuild = "";
  /** The connected unit's firmware version, or null while no unit is connected. */
  @property({ type: String }) firmwareVersion: string | null = null;
  @property({ attribute: false }) scheduleFunction: ScheduleFunction = (action, delayMs) =>
    setTimeout(action, delayMs);
  @property({ attribute: false }) cancelFunction: CancelFunction = (handle) =>
    clearTimeout(handle as ReturnType<typeof setTimeout>);
  @property({ attribute: false }) reloadFunction: () => void = () => window.location.reload();

  /** Null until the first read, and after a read that failed. */
  @state() private system: BridgeSystemDto | null = null;
  @state() private hasRead = false;

  private refreshHandle: unknown;

  get freshness(): PageFreshness {
    return readPageFreshness(this.system, this.pageBuild);
  }

  override connectedCallback(): void {
    super.connectedCallback();
    void this.readAndScheduleNext();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stopRefresh();
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      ${this.renderUnit(strings)} ${this.renderPage(strings)}
      ${this.system === null ? nothing : this.renderSystem(strings, this.system)}
    `;
  }

  private renderUnit(strings: UiStrings): TemplateResult {
    return this.renderRows(strings.systemUnitSection, [
      [strings.systemUnitFirmware, this.firmwareVersion ?? strings.deviceNotConnected],
    ]);
  }

  private renderPage(strings: UiStrings): TemplateResult {
    const freshness = this.freshness;
    const stateLabel = { live: strings.pageLive, cached: strings.pageCached, outdated: strings.pageOutdated }[freshness];
    return html`
      <section>
        <h3>${strings.systemPageSection}</h3>
        <dl>
          <dt>${strings.systemPageState}</dt>
          <dd><span class="freshness" data-freshness=${freshness}>${stateLabel}</span></dd>
          <dt>${strings.systemPageBuild}</dt>
          <dd>${this.pageBuild || UNKNOWN}</dd>
          ${this.system === null
            ? nothing
            : html`<dt>${strings.systemServedBuild}</dt><dd>${this.system.frontend_build ?? UNKNOWN}</dd>`}
        </dl>
        ${this.hasRead && freshness === "cached" ? html`<p class="hint">${strings.systemUnreachable}</p>` : nothing}
        ${freshness === "outdated"
          ? html`<p class="hint">
              ${strings.systemOutdatedHint}
              <button type="button" class="reload" @click=${() => this.reloadFunction()}>${strings.systemReload}</button>
            </p>`
          : nothing}
      </section>
    `;
  }

  private renderSystem(strings: UiStrings, system: BridgeSystemDto): TemplateResult {
    return html`
      ${this.renderRows(strings.systemMachineSection, this.machineRows(strings, system))}
      <section>
        <h3>${strings.systemMemorySection}</h3>
        ${this.renderUsage(strings.systemRam, system.memory_total_bytes, system.memory_available_bytes)}
        ${this.renderUsage(strings.systemSwap, system.swap_total_bytes, system.swap_free_bytes)}
        ${this.renderUsage(strings.systemDisk, system.disk_total_bytes, system.disk_free_bytes)}
        <dl>
          <dt>${strings.systemBackendMemory}</dt>
          <dd>${known(system.backend_memory_bytes, formatBytes)}</dd>
        </dl>
      </section>
      ${this.renderNetwork(strings, system.interfaces)}
    `;
  }

  private machineRows(strings: UiStrings, system: BridgeSystemDto): Row[] {
    const cores = system.cpu_count === null ? null : strings.systemCores.replace("{count}", String(system.cpu_count));
    const cpu = [cores, system.architecture, system.cpu_frequency_mhz === null ? null : `${Math.round(system.cpu_frequency_mhz)} MHz`]
      .filter((part) => part !== null)
      .join(" · ");
    return [
      [strings.systemHostname, system.hostname ?? UNKNOWN],
      [strings.systemModel, system.model ?? UNKNOWN],
      [strings.systemOperatingSystem, system.operating_system ?? UNKNOWN],
      [strings.systemKernel, system.kernel ?? UNKNOWN],
      [strings.systemPython, system.python_version ?? UNKNOWN],
      [strings.systemUptime, known(system.uptime_seconds, formatDuration)],
      [strings.systemLoad, known(system.load_average, (load) => load.map((value) => value.toFixed(2)).join(" "))],
      [strings.systemCpu, cpu || UNKNOWN],
      [strings.systemTemperature, known(system.cpu_temperature_celsius, (celsius) => `${celsius.toFixed(1)} °C`)],
      [strings.systemThrottled, system.throttled_flags ?? UNKNOWN],
    ];
  }

  private renderRows(title: string, rows: Row[]): TemplateResult {
    return html`
      <section>
        <h3>${title}</h3>
        <dl>${rows.map(([label, value]) => html`<dt>${label}</dt><dd>${value}</dd>`)}</dl>
      </section>
    `;
  }

  /** One meter: the used part of a total, as `df` and `free` show it. */
  private renderUsage(label: string, total: number | null, free: number | null): TemplateResult {
    if (total === null || free === null || total === 0) {
      return html`<div class="usage"><span class="usage-label">${label}</span><span class="usage-value">${UNKNOWN}</span></div>`;
    }
    const percent = usedPercent(total, free);
    return html`
      <div class="usage">
        <span class="usage-label">${label}</span>
        <span class="usage-value">${formatBytes(total - free)} / ${formatBytes(total)} · ${percent}%</span>
        <meter min="0" max="100" low="70" high="90" optimum="0" value=${percent} aria-label=${label}></meter>
      </div>
    `;
  }

  private renderNetwork(strings: UiStrings, interfaces: NetworkInterfaceDto[]): TemplateResult {
    return html`
      <section>
        <h3>${strings.systemNetworkSection}</h3>
        ${interfaces.length === 0
          ? html`<p class="hint">${strings.systemNoInterfaces}</p>`
          : html`<dl class="network">
              ${interfaces.map(
                (networkInterface) => html`
                  <dt>${networkInterface.name} <span class="state">${networkInterface.state}</span></dt>
                  <dd>${interfaceDetails(networkInterface)}</dd>
                `,
              )}
            </dl>`}
      </section>
    `;
  }

  private async read(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    try {
      this.system = await this.api.readBridgeSystem();
    } catch {
      // The Pi is out of reach. The page is then the cached copy.
      this.system = null;
    }
    this.hasRead = true;
  }

  private async readAndScheduleNext(): Promise<void> {
    await this.read();
    this.stopRefresh();
    if (!this.isConnected) {
      return;
    }
    this.refreshHandle = this.scheduleFunction(() => {
      void this.readAndScheduleNext();
    }, REFRESH_WHILE_OPEN_MS);
  }

  private stopRefresh(): void {
    if (this.refreshHandle !== undefined) {
      this.cancelFunction(this.refreshHandle);
      this.refreshHandle = undefined;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "system-panel": SystemPanel;
  }
}
