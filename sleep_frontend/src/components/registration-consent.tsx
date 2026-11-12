export default function RegistrationConsent() {
  return <fieldset style={{border:"1px solid #ded8e9",borderRadius:12,padding:14,margin:"16px 0",fontSize:13,lineHeight:1.7}}>
    <legend>개인정보·건강정보 수집 동의</legend>
    <p><a href="/privacy" target="_blank" rel="noopener noreferrer">처리 안내 전체 보기</a> · 운영자 윤재원</p>
    <label style={{display:"flex",flexDirection:"row",alignItems:"start",gap:8}}>
      <input style={{width:18,height:18,padding:0,flexShrink:0,minWidth:18,marginTop:5}} type="checkbox" name="privacy_consent" required />
      <span>아이디·비밀번호 해시·인증 정보를 계정 운영 목적으로 탈퇴 시까지 보관하는 데 동의합니다.</span>
    </label>
    <label style={{display:"flex",flexDirection:"row",alignItems:"start",gap:8}}>
      <input style={{width:18,height:18,padding:0,flexShrink:0,minWidth:18,marginTop:5}} type="checkbox" name="health_consent" required />
      <span>수면 시각·단계·심박·HRV 등 직접 제공하는 건강정보를 기록 분석과 규칙 기반 코칭에 사용하는 데 별도로 동의합니다. 삭제·탈퇴 시 운영 DB에서 삭제되며 복구 백업은 최대 7일 뒤 만료됩니다.</span>
    </label>
    <label style={{display:"flex",flexDirection:"row",alignItems:"start",gap:8}}>
      <input style={{width:18,height:18,padding:0,flexShrink:0,minWidth:18,marginTop:5}} type="checkbox" name="overseas_consent" required />
      <span>위 계정·건강정보를 서비스 요청 시 Render 싱가포르 서버에 HTTPS로 전송하고 계정·기록 삭제 시까지 저장하는 데 동의합니다. 복구 백업은 최대 7일 뒤 만료됩니다.</span>
    </label>
    <label style={{display:"flex",flexDirection:"row",alignItems:"start",gap:8}}>
      <input style={{width:18,height:18,padding:0,flexShrink:0,minWidth:18,marginTop:5}} type="checkbox" name="adult_confirmed" required />
      <span>만 19세 이상이며 본인의 기록만 제공함을 확인합니다.</span>
    </label>
    <p>동의하지 않으면 계정 서비스 이용은 제한되며 가상 기록 체험은 가능합니다. 문의: jwyoon114@gmail.com</p>
    <input type="hidden" name="policy_version" value="2026-11-12-v1" />
  </fieldset>;
}
