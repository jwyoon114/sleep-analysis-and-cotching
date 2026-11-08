import SwiftUI
import WebKit

@main struct DaljamApp:App {
 @Environment(\.scenePhase) private var phase
 var body:some Scene {
  WindowGroup { ContentView().task { await HealthSync.shared.resume() } }
   .onChange(of:phase) { state in
    if state == .active { Task { await HealthSync.shared.resume() } }
   }
 }
}
struct ContentView:View {
 @AppStorage("serverOrigin") private var origin=""
 @State private var input=""
 @State private var error=""
 @State private var confirm=false
 var body:some View {
  NavigationStack {
   if let url=URL(string:origin),!origin.isEmpty {
    DaljamWeb(origin:url).navigationTitle("달잠").navigationBarTitleDisplayMode(.inline)
     .toolbar { Button("서버 변경") { confirm=true } }
     .confirmationDialog("현재 휴대폰의 자동 연결을 해제하고 서버를 변경할까요?",isPresented:$confirm) {
      Button("연결 해제 후 변경",role:.destructive) {
       HealthSync.shared.disconnect()
       WKWebsiteDataStore.default().removeData(ofTypes:WKWebsiteDataStore.allWebsiteDataTypes(),modifiedSince:.distantPast) {}
       origin=""
      }
     }
   } else {
    Form {
     Section("달잠에 연결하기") {
      Text("PC에서 만든 HTTPS 주소를 입력하세요. 공개 서비스에는 고정 주소를 사용하세요.")
      TextField("https://달잠-서버-주소",text:$input).textInputAutocapitalization(.never).keyboardType(.URL).autocorrectionDisabled()
      Button("달잠 열기") {
       let value=input.trimmingCharacters(in:.whitespacesAndNewlines)
       guard let c=URLComponents(string:value),c.scheme=="https",c.host != nil,c.user==nil,c.password==nil,c.query==nil,c.fragment==nil,c.path.isEmpty || c.path=="/",let url=c.url else { error="경로가 없는 HTTPS 주소를 입력해 주세요.";return }
       origin=url.absoluteString.trimmingCharacters(in:CharacterSet(charactersIn:"/"));error=""
      }
      if !error.isEmpty { Text(error).foregroundStyle(.red) }
     }
    }.navigationTitle("달잠")
   }
  }
 }
}
struct DaljamWeb:UIViewRepresentable {
 let origin:URL
 func makeCoordinator()->Coordinator { Coordinator(origin:origin) }
 func makeUIView(context:Context)->WKWebView {
  let config=WKWebViewConfiguration()
  config.userContentController.add(context.coordinator,name:"DaljamBridge")
  if let path=Bundle.main.url(forResource:"bridge",withExtension:"js"),let script=try? String(contentsOf:path,encoding:.utf8) {
   config.userContentController.addUserScript(WKUserScript(source:script,injectionTime:.atDocumentStart,forMainFrameOnly:true))
  }
  let web=WKWebView(frame:.zero,configuration:config)
  web.navigationDelegate=context.coordinator;web.uiDelegate=context.coordinator;context.coordinator.web=web
  web.load(URLRequest(url:origin));return web
 }
 func updateUIView(_ uiView:WKWebView,context:Context) {}
 static func dismantleUIView(_ uiView:WKWebView,coordinator:Coordinator) {
  uiView.configuration.userContentController.removeScriptMessageHandler(forName:"DaljamBridge");uiView.stopLoading()
 }
 final class Coordinator:NSObject,WKScriptMessageHandler,WKNavigationDelegate,WKUIDelegate {
  let origin:URL
  weak var web:WKWebView?
  init(origin:URL) { self.origin=origin }
  func sameOrigin(_ url:URL)->Bool { url.scheme==origin.scheme && url.host==origin.host && (url.port ?? 443)==(origin.port ?? 443) }
  func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage) {
   let security=message.frameInfo.securityOrigin
   guard message.frameInfo.isMainFrame,security.protocol=="https",security.host==origin.host,(security.port==0 ? 443:security.port)==(origin.port ?? 443),
         let body=message.body as? [String:Any],let id=body["id"] as? String,id.count<=100 else { return }
   Task { @MainActor in
    do {
     let service=HealthSync.shared
     let result:[String:Any]
     switch body["method"] as? String {
      case "status":result=service.status()
      case "authorize":result=["sources":try await service.authorize()]
      case "configure":try await service.configure(body["payload"] as? [String:Any] ?? [:],origin:origin.absoluteString);result=service.status()
      case "disconnect":service.disconnect();result=service.status()
      case "sync":result=try await service.sync()
      default:throw service.failure("지원하지 않는 연결 요청입니다.")
     }
     reply(["id":id,"result":result])
    } catch { reply(["id":id,"error":error.localizedDescription]) }
   }
  }
  @MainActor func reply(_ result:[String:Any]) {
   guard let url=web?.url,sameOrigin(url),let data=try? JSONSerialization.data(withJSONObject:result),let json=String(data:data,encoding:.utf8) else { return }
   web?.evaluateJavaScript("window.__daljamReply(\(json));",completionHandler:nil)
  }
  func webView(_ webView:WKWebView,decidePolicyFor action:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
   guard let url=action.request.url else { decisionHandler(.cancel);return }
   if action.targetFrame?.isMainFrame==false { decisionHandler(.allow);return }
   if sameOrigin(url) { decisionHandler(.allow) }
   else { if url.scheme=="https" { UIApplication.shared.open(url) };decisionHandler(.cancel) }
  }
  func webView(_ webView:WKWebView,createWebViewWith configuration:WKWebViewConfiguration,for navigationAction:WKNavigationAction,windowFeatures:WKWindowFeatures)->WKWebView? {
   if let url=navigationAction.request.url,url.scheme=="https" { UIApplication.shared.open(url) };return nil
  }
 }
}
