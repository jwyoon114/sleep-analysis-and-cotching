package app.daljam.mobile

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.*
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.PermissionController
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainActivity:ComponentActivity(){
 private lateinit var service:HealthSync
 private var web:WebView?=null
 private var permissionReply:((JSONObject?,String?)->Unit)?=null
 private var origin=""
 private val permission=registerForActivityResult(PermissionController.createRequestPermissionResultContract()){
  val reply=permissionReply;permissionReply=null
  lifecycleScope.launch{try{reply?.invoke(JSONObject().put("sources",service.sources()),null)}catch(e:Exception){reply?.invoke(null,e.message)}}
 }
 override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);service=HealthSync(this)
  val saved=getSharedPreferences("server",MODE_PRIVATE).getString("origin",null)
  if(saved==null)setup()else open(saved)
 }
 override fun onResume(){super.onResume();if(::service.isInitialized&&service.config()!=null)lifecycleScope.launch{try{service.sync()}catch(_:Exception){}}}
 private fun setup(){
  val layout=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(40,80,40,40)}
  layout.addView(TextView(this).apply{text="달잠에 연결하기\nPC에서 만든 HTTPS 주소를 입력하세요. 공개 서비스에는 고정 주소를 사용하세요.";textSize=19f})
  val input=EditText(this).apply{hint="https://달잠-서버-주소";inputType=android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI};layout.addView(input)
  layout.addView(Button(this).apply{text="달잠 열기";setOnClickListener{try{
   val u=Uri.parse(input.text.toString().trim())
   require(u.scheme=="https"&&!u.host.isNullOrBlank()&&u.userInfo==null&&(u.path.isNullOrEmpty()||u.path=="/")&&u.query==null&&u.fragment==null)
   val value="https://"+u.encodedAuthority;getSharedPreferences("server",MODE_PRIVATE).edit().putString("origin",value).apply();open(value)
  }catch(_:Exception){input.error="경로가 없는 HTTPS 주소를 입력해 주세요."}}})
  setContentView(layout)
 }
 @SuppressLint("SetJavaScriptEnabled")
 private fun open(value:String){
  origin=value
  if(!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)){AlertDialog.Builder(this).setMessage("Android System WebView를 업데이트한 뒤 다시 열어 주세요.").setPositiveButton("확인",null).show();return}
  val view=WebView(this);web=view
  view.settings.javaScriptEnabled=true;view.settings.domStorageEnabled=true
  view.settings.allowFileAccess=false;view.settings.allowContentAccess=false;view.settings.mixedContentMode=WebSettings.MIXED_CONTENT_NEVER_ALLOW
  CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(view,false)
  WebViewCompat.addWebMessageListener(view,"DaljamBridge",setOf(origin)){_,message,source,isMain,reply->
   if(!isMain||source.toString().trimEnd('/')!=origin)return@addWebMessageListener
   val data=try{JSONObject(message.data ?: "")}catch(_:Exception){return@addWebMessageListener}
   val id=data.optString("id").take(100)
   val respond:(JSONObject?,String?)->Unit={result,error->reply.postMessage(JSONObject().put("id",id).put("result",result?:JSONObject.NULL).put("error",error?:JSONObject.NULL).toString())}
   lifecycleScope.launch{try{
    when(data.optString("method")){
     "status"->respond(service.status(),null)
     "authorize"->{
      check(service.available()){"Health Connect를 설치하거나 업데이트해 주세요."}
      check(permissionReply==null){"이미 권한을 확인 중이에요."}
      permissionReply=respond
      val required=mutableSetOf(HealthSync.READ)
      if(service.client.features.getFeatureStatus(HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND)==HealthConnectFeatures.FEATURE_STATUS_AVAILABLE)required.add(HealthSync.BACKGROUND)
      permission.launch(required)
     }
     "configure"->{service.configure(data.getJSONObject("payload"),origin);respond(service.status(),null)}
     "disconnect"->{service.disconnect();respond(service.status(),null)}
     "sync"->respond(service.sync(),null)
     else->error("지원하지 않는 연결 요청입니다.")
    }
   }catch(e:Exception){permissionReply=null;respond(null,e.message?:"건강앱 연결을 확인해 주세요.")}}
  }
  view.webViewClient=object:WebViewClient(){
   override fun shouldOverrideUrlLoading(view:WebView,request:WebResourceRequest):Boolean{
    if(!request.isForMainFrame)return false
    val u=request.url
    if(u.scheme+"://"+u.encodedAuthority==origin)return false
    if(u.scheme=="https")startActivity(Intent(Intent.ACTION_VIEW,u))
    return true
   }
   override fun onPageFinished(view:WebView,url:String){
    if(url.startsWith(origin+"/")||url==origin)view.evaluateJavascript(assets.open("bridge.js").bufferedReader().use{it.readText()},null)
   }
  }
  val layout=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
  layout.addView(Button(this).apply{text="달잠 · 서버 변경";setOnClickListener{
   AlertDialog.Builder(this@MainActivity).setMessage("현재 휴대폰의 자동 연결을 해제하고 서버를 변경할까요?")
    .setPositiveButton("변경"){_,_->service.disconnect();CookieManager.getInstance().removeAllCookies(null);getSharedPreferences("server",MODE_PRIVATE).edit().clear().apply();web?.destroy();web=null;setup()}
    .setNegativeButton("취소",null).show()
  }})
  layout.addView(view,LinearLayout.LayoutParams(-1,0,1f));setContentView(layout);view.loadUrl(origin)
 }
}
class PrivacyActivity:ComponentActivity(){
 override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState)
  setContentView(TextView(this).apply{setPadding(40,60,40,40);textSize=18f
   text="달잠 건강 데이터 사용 안내\n\n수면 시간과 수면 단계만 읽어 사용자가 지정한 달잠 서버로 전송하고 분석합니다. 건강앱에는 기록을 쓰지 않습니다.\n\nAI 조언 자동 생성을 켜면 서버의 AI 서비스로 최신 수면 기록을 보내 조언을 만듭니다.\n\n건강앱 설정에서 읽기 권한을 철회하거나 달잠에서 연결을 해제할 수 있습니다. 저장된 기록은 분석 기록·휴지통에서 삭제할 수 있습니다.\n\n백그라운드 동기화는 기기와 운영체제 상태에 따라 지연될 수 있습니다."
  })
 }
}
