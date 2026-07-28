from __future__ import annotations


PATIENT_TERMS_VERSION = "draft-2026-07-28-v0.1"
PRIVACY_POLICY_VERSION = "draft-2026-07-28-v0.1"
LEGAL_DOCUMENT_STATUS_JA = "弁護士レビュー用ドラフト（未確定）"
LEGAL_DOCUMENT_STATUS_EN = "Draft for legal review (not final)"


def build_service_consent_record(timestamp: str) -> dict[str, object]:
    """Return the versioned audit fields recorded for each service submission."""
    return {
        "consent_checked": True,
        "consent_method": "in_app_checkbox_before_submission",
        "terms_consent_checked": True,
        "patient_terms_version": PATIENT_TERMS_VERSION,
        "privacy_policy_acknowledged": True,
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "terms_consent_timestamp": timestamp,
    }


def patient_terms_markdown(
    language: str,
    *,
    service_provider: str,
    facility_name: str,
    contact_email: str,
) -> str:
    if language == "日本語":
        return f"""
## 患者向け利用規約

**{LEGAL_DOCUMENT_STATUS_JA}**  
版：{PATIENT_TERMS_VERSION}

### 1. 本サービスについて
- 本サービスは、医療機関の管理下で、患者報告アウトカム（PRO）等の入力、採点、経時的な整理および医療者による確認を補助するものです。
- 本サービスは診断、治療方針、薬剤選択、治療の継続・変更・中止を自動的に決定するものではありません。最終的な診療判断は医師その他の資格を有する医療者が行います。
- 緊急時の連絡、救急相談または医療者への緊急通知には使用できません。急な症状悪化等がある場合は、医療機関または地域の救急窓口へ直接連絡してください。

### 2. 提供関係と利用料金
- 本サービスは、{service_provider}が医療機関向けに提供する診療・問診支援基盤です。本画面は、{facility_name}の案内に基づいて患者さんが利用します。
- 医療機関との契約内容により、本サービスが有償で提供される場合があります。患者さんに対する本サービス単独の利用料金の有無や診療費上の取扱いは、医療機関の案内に従ってください。

### 3. 利用条件
- 医療機関から案内された施設専用URLまたはQRコードを使用し、案内された匿名コードを正確に入力してください。
- 氏名、生年月日、住所、電話番号、メールアドレス、患者ID、診察券番号、保険証番号、マイナンバー等の直接個人を特定できる情報を入力しないでください。
- 匿名コード欄その他の入力欄に、第三者の情報、不正確な内容、またはサービスの運用を妨げる内容を入力しないでください。

### 4. 表示結果
- スコア、推移、注意表示等は、医療者による確認を補助する参考情報です。表示結果のみを根拠に患者さん自身で診断または治療変更を行わないでください。
- 通信障害、保守、外部サービスの障害その他の事情により、サービスの全部または一部を一時的に利用できない場合があります。

### 5. 質問票等の権利
- 質問票の名称、設問、翻訳、採点方法等には、各権利者の著作権、商標権、ライセンス条件または利用条件が適用される場合があります。
- 画面の複製、転載、再配布または本来の診療目的を超える利用は、権利者の条件に従う必要があります。

### 6. 研究利用
- 診療支援としての本サービス利用に関する同意と、研究参加への同意は別のものです。
- 入力情報を研究に利用する場合は、対象となる研究について別途説明し、必要な同意または倫理上・法令上の手続を行います。研究参加を断っても、通常の診療上の不利益はありません。

### 7. 規約の変更
- 法令、サービス内容または契約内容の変更等に応じて本規約を改訂する場合があります。重要な変更は、画面表示その他の適切な方法で案内します。
- 送信時に同意した規約の版と日時を記録します。

### 8. お問い合わせ
- 診療内容、匿名コードまたは患者情報との対応関係：利用している医療機関
- 本サービスの操作・運用：{contact_email}
"""

    return f"""
## Patient Terms of Use

**{LEGAL_DOCUMENT_STATUS_EN}**  
Version: {PATIENT_TERMS_VERSION}

### 1. About the service
- This service supports patient-reported outcome (PRO) entry, scoring, longitudinal organization, and review by healthcare professionals under the management of a medical institution.
- It does not automatically diagnose disease or determine treatment, medication selection, or treatment continuation, change, or discontinuation. Final clinical decisions are made by qualified healthcare professionals.
- It must not be used for emergencies, urgent consultation, or emergency notification to clinicians. Contact the medical institution or the appropriate local emergency service directly if symptoms suddenly worsen.

### 2. Service relationship and fees
- {service_provider} provides this clinical and questionnaire-support platform to medical institutions. Patients use this screen as directed by {facility_name}.
- The service may be provided to the medical institution under a paid agreement. Follow the medical institution's guidance regarding any patient charge or treatment-related fee.

### 3. Conditions of use
- Use the facility-specific URL or QR code and enter the anonymous code provided by the medical institution.
- Do not enter direct identifiers, including names, dates of birth, addresses, phone numbers, email addresses, patient or medical-record numbers, insurance numbers, or government identification numbers.
- Do not enter another person's information, inaccurate content, or content that interferes with operation of the service.

### 4. Displayed results
- Scores, trends, and alerts are reference information that supports review by healthcare professionals. Patients must not independently diagnose a condition or change treatment based only on the displayed results.
- The service may be temporarily unavailable because of maintenance, network failure, third-party service failure, or other operational circumstances.

### 5. Rights in questionnaires
- Questionnaire names, wording, translations, scoring methods, and related materials may be subject to third-party copyrights, trademarks, licenses, and conditions of use.
- Copying, redistribution, or use beyond the intended clinical purpose must comply with the applicable rights holder's conditions.

### 6. Research use
- Agreement to use this clinical-support service is separate from consent to participate in research.
- If submitted information is to be used for research, the relevant study will be explained separately and the required consent or other legal and ethical procedures will be followed. Refusal to participate in research will not disadvantage ordinary clinical care.

### 7. Changes
- These terms may be revised following changes in law, the service, or contractual arrangements. Material changes will be communicated through the application or another appropriate method.
- The version and time accepted at submission are recorded.

### 8. Contact
- Clinical care, anonymous codes, and links to patient identity: the medical institution using the service
- Service operation and support: {contact_email}
"""


def privacy_policy_markdown(
    language: str,
    *,
    service_provider: str,
    facility_name: str,
    contact_email: str,
    hosting_region: str,
) -> str:
    if language == "日本語":
        return f"""
## プライバシーポリシー

**{LEGAL_DOCUMENT_STATUS_JA}**  
版：{PRIVACY_POLICY_VERSION}

### 1. 適用範囲と取扱主体
- 本ポリシーは、{facility_name}の案内により利用する患者向け入力画面と、そのデータを扱う医療機関向け機能に適用します。
- 医療機関は、患者さんへの案内、匿名コードと患者情報の対応管理および診療上の利用を担います。{service_provider}は、医療機関向けシステムの提供・保守・安全管理を担います。
- 個人情報保護法上の立場、責任分担および問い合わせ対応の詳細は、医療機関向け契約・利用規約で定めます。**［弁護士確認事項］**

### 2. 取り扱う情報
- 施設ID、匿名コード、対象疾患、質問票の種類、回答、スコア、送信日時、入力所要時間、入力支援の有無、入力しやすさ等
- 研究対象の場合に限り、研究同意の有無、同意した説明文書の版および同意日時
- 同意した患者向け利用規約・本ポリシーの版、確認日時および確認方法
- セキュリティ確保や障害調査に必要なアクセス・運用ログ。利用するインフラ事業者において、IPアドレス、ブラウザ情報等が一時的に処理・記録される場合があります。**［保存項目・期間は運用確認後に確定］**
- 氏名等の直接識別子は入力しない設計ですが、医療機関が保有する対応表と照合できる匿名コード化情報は、常に法的な意味での「匿名情報」とは限りません。適用法令と契約に従って安全に取り扱います。

### 3. 利用目的
- 医療機関における問診、診療補助、スコア確認および経時的な状態把握
- サービスの提供、本人・施設の利用確認、問い合わせ対応、障害対応、セキュリティ確保および不正利用防止
- 個人を直接識別しない集計による、品質評価、機能改善および運用状況の分析
- 医療機関との契約、請求、プラン管理その他の施設単位の事務処理
- 研究利用は、別途示す研究計画、説明・同意または適用される倫理上・法令上の手続の範囲に限ります。

### 4. 外部委託・国外での取扱い
- サービス提供のため、クラウドホスティング、マネージドデータベース、通知・監視等の事業者に取扱いを委託する場合があります。委託先を必要な範囲で選定・監督します。
- 現在のホスティングおよびデータベースの設定地域は **{hosting_region}** です。このため、データが日本国外で保存または処理される場合があります。実運用時の契約、本人への情報提供、国外移転に関する措置は、提供形態に応じて確認・整備します。**［弁護士確認事項］**

### 5. 第三者提供
- 法令に基づく場合、生命・身体の保護に必要な場合その他法令上認められる場合を除き、本人の同意なく第三者へ提供しません。
- 医療機関からの委託に基づくサービス提供、保守または安全管理のために必要な範囲で委託先へ取り扱わせる場合があります。第三者提供と委託の法的整理は契約関係に応じて確定します。**［弁護士確認事項］**

### 6. 安全管理
- 施設IDに基づくデータ分離、施設専用アクセス情報、通信の暗号化、アクセス制御、認証情報のハッシュ化、ログ確認、バックアップ等の措置を組み合わせます。
- 医療機関は、匿名コードと患者情報の対応表、施設用ID・パスワードおよび患者案内用URLを適切に管理します。

### 7. 保存期間・削除
- 診療上必要な期間、医療機関との契約期間、法令上必要な期間およびバックアップ運用に必要な期間を考慮して保存し、利用目的を達成した情報は医療機関との取り決めに従って削除または識別性を低減します。
- 具体的な保存期間、契約終了時の返却・削除方法およびバックアップからの消去時期は、医療機関向け契約・運用基準で定めます。**［弁護士・施設確認事項］**

### 8. 開示・訂正・削除等
- 診療情報、匿名コードとの対応、回答の訂正・削除等は、まず利用している医療機関へお問い合わせください。
- 本サービスにおける個人情報の取扱いに関する問い合わせは、{contact_email}でも受け付けます。本人確認と医療機関との関係を確認した上で、適用法令と契約に従って対応します。

### 9. 改訂
- 本ポリシーを改訂する場合は、改訂日と版を表示し、重要な変更は適切な方法で案内します。送信時に確認した版と日時を記録します。
"""

    return f"""
## Privacy Policy

**{LEGAL_DOCUMENT_STATUS_EN}**  
Version: {PRIVACY_POLICY_VERSION}

### 1. Scope and responsible parties
- This policy applies to the patient input screen used under the direction of {facility_name} and to the medical-institution functions that process its data.
- The medical institution manages patient instructions, the link between anonymous codes and patient identities, and clinical use. {service_provider} provides, maintains, and secures the system for the medical institution.
- The parties' exact legal roles, responsibilities, and inquiry procedures will be defined in the institutional agreement and terms. **[For legal review]**

### 2. Information processed
- Facility ID, anonymous code, condition, questionnaire type, responses, scores, submission time, input duration, input assistance, ease-of-use feedback, and related fields
- For applicable research only: research-consent status, consent-document version, and consent time
- Versions of the Patient Terms and this Policy acknowledged, acknowledgement time, and method
- Access and operational logs needed for security and incident investigation. Infrastructure providers may temporarily process or retain IP addresses, browser information, and related technical data. **[Exact fields and retention to be confirmed operationally]**
- Although the service is designed not to collect direct identifiers, coded data that a medical institution can link through its correspondence table is not necessarily legally anonymous. It will be protected according to applicable law and contract.

### 3. Purposes
- Questionnaire collection, clinical support, score review, and longitudinal monitoring by the medical institution
- Service delivery, facility/use verification, support, incident response, security, and fraud or misuse prevention
- Quality assessment, feature improvement, and operational analysis using aggregates that do not directly identify patients
- Institutional contracting, billing, plan administration, and related facility-level operations
- Research use is limited to the separately described study plan and the applicable consent, ethical, and legal procedures.

### 4. Service providers and international processing
- Cloud hosting, managed database, notification, monitoring, and related providers may process data as service providers. Appropriate selection and oversight measures will be used.
- The current configured hosting and database region is **{hosting_region}**. Data may therefore be stored or processed outside Japan. Contractual controls, user information, and measures for international handling will be finalized for each service model. **[For legal review]**

### 5. Disclosure to third parties
- Data will not be disclosed to third parties without consent except where permitted or required by applicable law, including circumstances necessary to protect life or physical safety.
- Vendors may process data to the extent needed to provide, maintain, and secure the service for the medical institution. The legal classification of disclosure and outsourced processing will be finalized according to the contractual structure. **[For legal review]**

### 6. Security
- Measures include facility-ID data separation, facility-specific access information, encryption in transit, access control, hashing of authentication credentials, log review, and backups.
- Medical institutions must appropriately protect the patient correspondence table, facility credentials, and patient-entry URLs.

### 7. Retention and deletion
- Information is retained with regard to clinical need, the institutional contract, applicable legal requirements, and backup operations. Information no longer needed will be deleted or made less identifiable according to the agreement with the medical institution.
- Exact retention periods, return or deletion on contract termination, and backup deletion schedules will be defined in the institutional agreement and operational standard. **[For legal and institutional review]**

### 8. Access, correction, and deletion requests
- Contact the medical institution first regarding clinical information, the patient-code link, or correction or deletion of responses.
- Questions about processing within this service may also be sent to {contact_email}. Requests will be handled after appropriate identity and institutional relationship verification, in accordance with applicable law and contract.

### 9. Revisions
- Revisions will identify the date and version, and material changes will be communicated appropriately. The version and time acknowledged at submission are recorded.
"""
