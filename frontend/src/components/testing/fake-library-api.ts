import { ApiError, type LibraryApi } from "../../api/client.ts";
import type { LibraryExportDto, LibraryImportDto } from "../../dto/profile.dto.ts";

/** A LibraryApi with one library in memory. An import counts an item as
 * skipped when the library holds one with the same name, as the backend
 * does for an unchanged item. It refuses a file of another format with a
 * 422, as the backend's check does. */
export class FakeLibraryApi implements LibraryApi {
  library: LibraryExportDto;
  failWith: Error | null = null;

  constructor(library: LibraryExportDto) {
    this.library = library;
  }

  async exportLibrary(): Promise<LibraryExportDto> {
    this.throwIfFailing();
    return this.library;
  }

  async importLibrary(library: LibraryExportDto): Promise<LibraryImportDto> {
    this.throwIfFailing();
    if (library.format !== "deq-tune-library") {
      throw new ApiError(422, "this is not a deq-tune-library file");
    }
    const profileNames = new Set(this.library.profiles.map((profile) => profile.name));
    const equalizerNames = new Set(this.library.equalizers.map((equalizer) => equalizer.name));
    const newProfiles = library.profiles.filter((profile) => !profileNames.has(profile.name));
    const newEqualizers = library.equalizers.filter((equalizer) => !equalizerNames.has(equalizer.name));
    this.library = {
      ...this.library,
      profiles: [...this.library.profiles, ...newProfiles],
      equalizers: [...this.library.equalizers, ...newEqualizers],
    };
    return {
      profiles_added: newProfiles.length,
      equalizers_added: newEqualizers.length,
      skipped: library.profiles.length - newProfiles.length + library.equalizers.length - newEqualizers.length,
      stars_added: 0,
    };
  }

  private throwIfFailing(): void {
    if (this.failWith !== null) {
      throw this.failWith;
    }
  }
}
