# SPDX-License-Identifier: Apache-2.0
Pod::Spec.new do |s|
  s.name           = 'OneMindPrivateFiles'
  s.version        = '0.1.0'
  s.summary        = 'OneMind private files'
  s.description    = 'Excludes private app databases from device backups.'
  s.homepage       = 'https://github.com/onemindos/ONEMINDOS'
  s.license        = 'Apache-2.0'
  s.author         = 'OneMind OS'
  s.source         = { git: 'https://github.com/onemindos/ONEMINDOS.git' }
  s.platforms      = { ios: '15.1' }
  s.source_files   = '*.swift'
  s.dependency 'ExpoModulesCore'
end
