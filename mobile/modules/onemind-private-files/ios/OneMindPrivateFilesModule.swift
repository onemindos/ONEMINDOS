// SPDX-License-Identifier: Apache-2.0
import ExpoModulesCore
import Foundation

public class OneMindPrivateFilesModule: Module {
  public func definition() -> ModuleDefinition {
    Name("OneMindPrivateFiles")

    AsyncFunction("excludeDatabaseDirectoryFromBackup") {
      let documents = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask,
                                                   appropriateFor: nil, create: false)
      var directory = documents.appendingPathComponent("onemind-app-databases", isDirectory: true)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      var values = URLResourceValues()
      values.isExcludedFromBackup = true
      try directory.setResourceValues(values)
    }
  }
}
