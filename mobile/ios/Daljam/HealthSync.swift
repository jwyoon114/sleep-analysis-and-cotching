import Foundation
import HealthKit
import Security

@MainActor final class HealthSync {
 static let shared = HealthSync()
 let store = HKHealthStore()
 let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!
 var observer: HKObserverQuery?
 var background = false
 private var flight: Task<[String: Any], Error>?
 private let key = "app.daljam.health-connection"
 private let defaults = UserDefaults.standard
 private let iso = ISO8601DateFormatter()
 nonisolated func failure(_ message: String) -> NSError { NSError(domain: "Daljam", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
 func config() -> [String: String]? {
  let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:key,kSecAttrAccount as String:"connection",kSecReturnData as String:true]
  var result: CFTypeRef?
  guard SecItemCopyMatching(query as CFDictionary,&result) == errSecSuccess, let data = result as? Data else { return nil }
  return (try? JSONSerialization.jsonObject(with:data)) as? [String:String]
 }
 func configure(_ payload: [String:Any], origin: String) async throws {
  guard let token = payload["token"] as? String, token.count >= 40, let account = payload["accountId"] as? String, let source = payload["sourceId"] as? String else { throw failure("건강앱 연결 정보를 확인해 주세요.") }
  let values = ["token":token,"accountId":account,"sourceId":source,"sourceName":payload["sourceName"] as? String ?? "Apple 건강","origin":origin]
  let data = try JSONSerialization.data(withJSONObject:values)
  let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:key,kSecAttrAccount as String:"connection"]
  SecItemDelete(query as CFDictionary)
  var item=query;item[kSecValueData as String]=data;item[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
  guard SecItemAdd(item as CFDictionary,nil) == errSecSuccess else { throw failure("연결 정보를 안전하게 저장하지 못했어요.") }
  defaults.removeObject(forKey:"healthError");await observe()
 }
 func disconnect() {
  flight?.cancel();flight=nil
  let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:key,kSecAttrAccount as String:"connection"]
  SecItemDelete(query as CFDictionary)
  if let observer { store.stop(observer);self.observer=nil }
  store.disableBackgroundDelivery(for:sleep) { _,_ in }
  background=false;defaults.removeObject(forKey:"healthLast");defaults.removeObject(forKey:"healthError")
 }
 func status() -> [String:Any] {
  let cfg=config()
  return ["available":HKHealthStore.isHealthDataAvailable(),"provider":"healthkit","connected":cfg != nil,"accountId":cfg?["accountId"] ?? "","lastSyncedAt":defaults.string(forKey:"healthLast") ?? "","error":defaults.string(forKey:"healthError") ?? "","background":background]
 }
 func authorize() async throws -> [[String:String]] {
  guard HKHealthStore.isHealthDataAvailable() else { throw failure("이 기기는 건강 데이터를 지원하지 않아요.") }
  try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void,Error>) in
   store.requestAuthorization(toShare:[],read:[sleep]) { success,error in
    if let error { continuation.resume(throwing:error) }
    else if success { continuation.resume() }
    else { continuation.resume(throwing:self.failure("건강앱의 수면 읽기 권한을 확인해 주세요.")) }
   }
  }
  let now=Date();let samples=try await samples(from:now.addingTimeInterval(-30*86400),to:now)
  var sources:[String:String]=[:]
  for sample in samples where stage(sample.value) != nil { sources[sourceID(sample)]=sample.sourceRevision.source.name+" · "+(sample.device?.name ?? "수면 기록") }
  return sources.map { ["id":$0.key,"name":String($0.value.prefix(120))] }.sorted { $0["name"]! < $1["name"]! }
 }
 func sourceID(_ sample:HKCategorySample) -> String {
  sample.sourceRevision.source.bundleIdentifier+"|"+(sample.device?.localIdentifier ?? sample.device?.productType ?? sample.device?.name ?? "")
 }
 func stage(_ value:Int) -> String? {
  switch value {
   case HKCategoryValueSleepAnalysis.awake.rawValue:return "wake"
   case HKCategoryValueSleepAnalysis.asleepCore.rawValue:return "core"
   case HKCategoryValueSleepAnalysis.asleepDeep.rawValue:return "deep"
   case HKCategoryValueSleepAnalysis.asleepREM.rawValue:return "rem"
   case HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue:return "unspecified"
   default:return nil
  }
 }
 func samples(from:Date,to:Date) async throws -> [HKCategorySample] {
  try await withCheckedThrowingContinuation { continuation in
   let predicate=HKQuery.predicateForSamples(withStart:from,end:to,options:[])
   let query=HKSampleQuery(sampleType:sleep,predicate:predicate,limit:20001,sortDescriptors:nil) { _,rows,error in
    if let error { continuation.resume(throwing:error) }
    else { continuation.resume(returning:(rows as? [HKCategorySample] ?? []).filter { $0.endDate <= to && $0.endDate > from }) }
   }
   store.execute(query)
  }
 }
 func resume() async {
  guard let origin=defaults.string(forKey:"serverOrigin"), !origin.isEmpty, config()?["origin"]==origin else { if config() != nil { disconnect() };return }
  await observe();_ = try? await sync()
 }
 func observe() async {
  guard config() != nil, HKHealthStore.isHealthDataAvailable(), observer == nil else { return }
  let query=HKObserverQuery(sampleType:sleep,predicate:nil) { _,complete,error in
   Task { @MainActor in
    defer { complete() }
    guard error == nil else { return }
    _ = try? await self.sync()
   }
  }
  observer=query;store.execute(query)
  background=await withCheckedContinuation { continuation in
   store.enableBackgroundDelivery(for:sleep,frequency:.hourly) { success,_ in continuation.resume(returning:success) }
  }
 }
 func sync() async throws -> [String:Any] {
  if let flight { return try await flight.value }
  let task=Task { try await self.performSync() };flight=task
  defer { flight=nil }
  return try await task.value
 }
 private func performSync() async throws -> [String:Any] {
  guard let cfg=config(),let source=cfg["sourceId"],let token=cfg["token"],let origin=cfg["origin"] else { throw failure("건강앱을 먼저 연결해 주세요.") }
  do {
   let end=Date(),start=end.addingTimeInterval(-30*86400)
   let all=try await samples(from:start,to:end)
   guard all.count <= 20000 else { throw failure("수면 기록이 너무 많아 동기화를 중단했어요.") }
   let records:[[String:Any]]=all.compactMap { sample in
    guard sourceID(sample)==source,let stage=stage(sample.value) else { return nil }
    let a=iso.string(from:sample.startDate),b=iso.string(from:sample.endDate)
    return ["id":sample.uuid.uuidString,"start":a,"end":b,"segments":[["start":a,"end":b,"stage":stage]]]
   }
   // HealthKit intentionally cannot distinguish denied read access from no data.
   // Empty results must never erase the server's previously imported nights.
   guard !records.isEmpty else { throw failure("접근 가능한 수면 기록이 없어요. 건강앱의 기록과 수면 읽기 권한을 확인해 주세요.") }
   let payload:[String:Any]=["provider":"healthkit","source_id":source,"timezone":TimeZone.current.identifier,"window_start":iso.string(from:start),"window_end":iso.string(from:end),"records":records]
   let data=try JSONSerialization.data(withJSONObject:payload)
   guard data.count <= 3*1024*1024,let url=URL(string:origin+"/api/mobile/health-sync") else { throw failure("연결 주소 또는 기록 크기를 확인해 주세요.") }
   try Task.checkCancellation()
   let session=URLSession(configuration:.ephemeral,delegate:NoRedirect(),delegateQueue:nil)
   defer { session.finishTasksAndInvalidate() }
   var request=URLRequest(url:url);request.httpMethod="POST";request.httpBody=data;request.timeoutInterval=55
   request.setValue("Bearer "+token,forHTTPHeaderField:"Authorization");request.setValue("application/json",forHTTPHeaderField:"Content-Type")
   let (response,info)=try await session.data(for:request)
   let result=(try? JSONSerialization.jsonObject(with:response)) as? [String:Any] ?? [:]
   let code=(info as? HTTPURLResponse)?.statusCode ?? 0
   guard (200..<300).contains(code) else { if code==401 { disconnect() };throw failure(result["detail"] as? String ?? "달잠 서버 연결을 확인해 주세요.") }
   if config()?["token"]==token { defaults.set(result["last_synced_at"] as? String,forKey:"healthLast");defaults.removeObject(forKey:"healthError") }
   return result
  } catch { defaults.set(String(error.localizedDescription.prefix(300)),forKey:"healthError");throw error }
 }
}
final class NoRedirect:NSObject,URLSessionTaskDelegate {
 func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest,completionHandler:@escaping(URLRequest?)->Void) { completionHandler(nil) }
}
