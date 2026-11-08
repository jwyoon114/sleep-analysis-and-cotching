package app.daljam.mobile

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.metadata.DataOrigin
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.work.*
import java.time.Instant
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.net.URL
import java.security.KeyStore
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject

class HealthSync(private val context: Context) {
    companion object {
        val mutex=Mutex()
        const val WORK="daljam-sleep-sync"
        const val BACKGROUND="android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND"
        val READ=HealthPermission.getReadPermission(SleepSessionRecord::class)
    }
    private val prefs=context.getSharedPreferences("health-sync",Context.MODE_PRIVATE)
    val client: HealthConnectClient get()=HealthConnectClient.getOrCreate(context)
    fun available()=HealthConnectClient.getSdkStatus(context)==HealthConnectClient.SDK_AVAILABLE
    private fun key():SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore").apply{load(null)}
        (store.getKey("daljam-health",null) as? SecretKey)?.let{return it}
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply{
            init(KeyGenParameterSpec.Builder("daljam-health",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun config():JSONObject? {
        return try {
            val packed=prefs.getString("credential",null) ?: return null
            val parts=packed.split(":");val cipher=Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,Base64.decode(parts[0],Base64.NO_WRAP)))
            JSONObject(String(cipher.doFinal(Base64.decode(parts[1],Base64.NO_WRAP)),Charsets.UTF_8))
        }catch(_:Exception){null}
    }
    fun configure(data:JSONObject,origin:String){
        require(data.getString("token").matches(Regex("[A-Za-z0-9_-]{40,200}")))
        require(data.getString("accountId").isNotBlank() && data.getString("sourceId").isNotBlank())
        val config=JSONObject(data.toString()).put("origin",origin)
        val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key())
        val encrypted=cipher.doFinal(config.toString().toByteArray(Charsets.UTF_8))
        check(prefs.edit().putString("credential",Base64.encodeToString(cipher.iv,Base64.NO_WRAP)+":"+Base64.encodeToString(encrypted,Base64.NO_WRAP)).remove("error").commit())
        val work=PeriodicWorkRequestBuilder<SyncWorker>(1,TimeUnit.HOURS).setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(WORK,ExistingPeriodicWorkPolicy.UPDATE,work)
    }
    fun disconnect(){prefs.edit().clear().commit();WorkManager.getInstance(context).cancelUniqueWork(WORK)}
    suspend fun background():Boolean=available() && client.features.getFeatureStatus(HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND)==HealthConnectFeatures.FEATURE_STATUS_AVAILABLE && BACKGROUND in client.permissionController.getGrantedPermissions()
    suspend fun status():JSONObject {
        val cfg=config()
        return JSONObject().put("available",available()).put("provider","health_connect").put("connected",cfg!=null)
            .put("accountId",cfg?.optString("accountId")).put("lastSyncedAt",prefs.getString("last",null))
            .put("error",prefs.getString("error",null)).put("background",try{background()}catch(_:Exception){false})
    }
    suspend fun records(first:Instant,last:Instant,source:String?=null):List<SleepSessionRecord>{
        val result=mutableListOf<SleepSessionRecord>();var page:String?=null
        do {
            val response=client.readRecords(ReadRecordsRequest(SleepSessionRecord::class,TimeRangeFilter.between(first,last),dataOriginFilter=if(source==null)emptySet()else setOf(DataOrigin(source)),pageSize=1000,pageToken=page))
            result.addAll(response.records.filter{it.endTime<=last && it.endTime>first})
            check(result.size<=20000){"수면 기록이 너무 많아요."}
            page=response.pageToken
        }while(page!=null)
        return result
    }
    suspend fun sources():JSONArray {
        check(READ in client.permissionController.getGrantedPermissions()){"수면 읽기 권한을 허용해 주세요."}
        val now=Instant.now();val packages=records(now.minus(30,ChronoUnit.DAYS),now).map{it.metadata.dataOrigin.packageName}.distinct().sortedBy{if(it=="com.sec.android.app.shealth")0 else 1}
        return JSONArray().apply{for(p in packages){val name=try{context.packageManager.getApplicationLabel(context.packageManager.getApplicationInfo(p,0)).toString()}catch(_:Exception){p};put(JSONObject().put("id",p).put("name",name.take(120)))}}
    }
    suspend fun sync():JSONObject=mutex.withLock {
        withContext(Dispatchers.IO){
            val cfg=config() ?: error("건강앱을 먼저 연결해 주세요.")
            try {
                check(available()){"Health Connect를 설치하거나 업데이트해 주세요."}
                check(READ in client.permissionController.getGrantedPermissions()){"수면 읽기 권한이 꺼졌어요. 연결을 해제한 뒤 다시 연결해 주세요."}
                val last=Instant.now();val first=last.minus(30,ChronoUnit.DAYS);val rows=JSONArray()
                for(r in records(first,last,cfg.getString("sourceId"))){
                    val stages=JSONArray()
                    for(s in r.stages){val stage=when(s.stage){1,3,7->"wake";2->"unspecified";4->"core";5->"deep";6->"rem";else->null} ?: continue
                        stages.put(JSONObject().put("start",s.startTime.toString()).put("end",s.endTime.toString()).put("stage",stage))}
                    rows.put(JSONObject().put("id",r.metadata.id).put("start",r.startTime.toString()).put("end",r.endTime.toString()).put("segments",stages))
                }
                // An empty result may reflect source permission changes.
                check(rows.length()>0){"접근 가능한 수면 기록이 없어요. 건강앱의 기록과 권한을 확인해 주세요."}
                val payload=JSONObject().put("provider","health_connect").put("source_id",cfg.getString("sourceId")).put("timezone",ZoneId.systemDefault().id).put("window_start",first.toString()).put("window_end",last.toString()).put("records",rows)
                val bytes=payload.toString().toByteArray(Charsets.UTF_8);check(bytes.size<=3*1024*1024){"동기화 기록이 너무 커요."}
                val conn=URL(cfg.getString("origin")+"/api/mobile/health-sync").openConnection() as HttpsURLConnection
                val result=try{
                    conn.requestMethod="POST";conn.instanceFollowRedirects=false;conn.connectTimeout=15000;conn.readTimeout=55000;conn.doOutput=true
                    conn.setRequestProperty("Authorization","Bearer "+cfg.getString("token"));conn.setRequestProperty("Content-Type","application/json");conn.setFixedLengthStreamingMode(bytes.size)
                    conn.outputStream.use{it.write(bytes)}
                    val code=conn.responseCode;val stream=if(code in 200..299)conn.inputStream else conn.errorStream
                    val response=stream?.bufferedReader()?.use{it.readText()} ?: "{}";val json=JSONObject(response)
                    if(code !in 200..299){if(code==401)disconnect();error(json.optString("detail","서버 연결을 확인해 주세요."))};json
                }finally{conn.disconnect()}
                // A user may have disconnected while the request was in flight.
                if(config()?.optString("token")==cfg.getString("token"))prefs.edit().putString("last",result.getString("last_synced_at")).remove("error").commit()
                result
            }catch(e:Exception){val message=if(e is SecurityException)"건강앱의 수면 읽기 권한을 확인해 주세요." else e.message ?: "서버에 연결하지 못했어요. 다음에 다시 시도합니다."
                prefs.edit().putString("error",message.take(300)).commit();throw IllegalStateException(message)}
        }
    }
}
class SyncWorker(context:Context,params:WorkerParameters):CoroutineWorker(context,params){
    override suspend fun doWork():Result {
        val service=HealthSync(applicationContext)
        if(service.config()==null)return Result.success()
        return try{if(!service.background())return Result.success();service.sync();Result.success()}catch(_:Exception){Result.retry()}
    }
}
