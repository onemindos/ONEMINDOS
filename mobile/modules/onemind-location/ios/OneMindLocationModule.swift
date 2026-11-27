// SPDX-License-Identifier: Apache-2.0
import CoreLocation
import ExpoModulesCore

public class OneMindLocationModule: Module {
  private lazy var bridge = LocationBridge()

  public func definition() -> ModuleDefinition {
    Name("OneMindLocation")

    AsyncFunction("getPermission") { (background: Bool) in
      self.bridge.permission(background)
    }.runOnQueue(.main)
    AsyncFunction("requestPermission") { (background: Bool, promise: Promise) in
      self.bridge.request(background, promise)
    }.runOnQueue(.main)
    AsyncFunction("currentPosition") { (background: Bool, promise: Promise) in
      self.bridge.current(background, promise)
    }.runOnQueue(.main)
  }
}

private final class LocationBridge: NSObject, CLLocationManagerDelegate {
  private let manager = CLLocationManager()
  private var permissionRequest: Promise?
  private var permissionTimeout: DispatchWorkItem?
  private var positionRequest: Promise?

  override init() {
    super.init()
    manager.delegate = self
  }

  func permission(_ background: Bool) -> [String: Any] {
    if background { return ["granted": false, "canAskAgain": false, "status": "unavailable"] }
    let status = manager.authorizationStatus
    let granted = status == .authorizedAlways || status == .authorizedWhenInUse
    let undetermined = status == .notDetermined
    return ["granted": granted, "canAskAgain": undetermined,
            "status": granted ? "granted" : undetermined ? "undetermined" : "denied"]
  }

  func request(_ background: Bool, _ promise: Promise) {
    let state = permission(background)
    guard state["canAskAgain"] as? Bool == true else { promise.resolve(state); return }
    guard permissionRequest == nil else {
      promise.reject("E_LOCATION_BUSY", "The phone is already asking for location access.")
      return
    }
    permissionRequest = promise
    manager.requestWhenInUseAuthorization()
    let timeout = DispatchWorkItem { [weak self] in self?.finishPermissionRequest() }
    permissionTimeout = timeout
    DispatchQueue.main.asyncAfter(deadline: .now() + 30, execute: timeout)
  }

  private func finishPermissionRequest() {
    guard let promise = permissionRequest else { return }
    permissionRequest = nil
    permissionTimeout?.cancel()
    permissionTimeout = nil
    promise.resolve(permission(false))
  }

  func current(_ background: Bool, _ promise: Promise) {
    guard !background else {
      promise.reject("E_LOCATION_UNAVAILABLE", "Background location is not available.")
      return
    }
    guard permission(false)["granted"] as? Bool == true else {
      promise.reject("E_LOCATION_PERMISSION", "Location access is off.")
      return
    }
    guard positionRequest == nil else {
      promise.reject("E_LOCATION_BUSY", "The phone is already finding its location.")
      return
    }
    positionRequest = promise
    manager.requestLocation()
  }

  func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
    if manager.authorizationStatus != .notDetermined { finishPermissionRequest() }
  }

  func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
    defer { positionRequest = nil }
    guard let fix = locations.last else {
      positionRequest?.reject("E_LOCATION_UNAVAILABLE", "The phone could not find its location.")
      return
    }
    positionRequest?.resolve(["latitude": fix.coordinate.latitude, "longitude": fix.coordinate.longitude,
                              "accuracyMeters": fix.horizontalAccuracy, "timestamp": fix.timestamp.timeIntervalSince1970 * 1000])
  }

  func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
    positionRequest?.reject("E_LOCATION_UNAVAILABLE", "The phone could not find its location.")
    positionRequest = nil
  }
}
