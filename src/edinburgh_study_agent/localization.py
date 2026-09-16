"""Small local catalog. Source documents are never sent to a translation service."""
from __future__ import annotations
import os
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LANGUAGES = {
    "en-GB": "English", "zh-Hans": "简体中文", "zh-Hant": "繁體中文",
    "fr-FR": "Français", "es-ES": "Español", "de-DE": "Deutsch",
    "ar": "العربية", "hi": "हिन्दी", "ja": "日本語", "ko": "한국어",
}
SERVICE_IDS = ("myed", "learn", "euclid", "enrolments", "timetable", "drps", "library",
               "resource_lists", "past_papers", "media", "careers", "internships", "careerhub",
               "career_events", "events", "eusa", "registry")
# The same stable IDs index each catalog; official names are always available separately.
TITLES = {
    "en-GB": "MyEd portal|Learn courses and materials|EUCLID student record|Enrolled courses|Personal timetable|Degree regulations and programmes|Library|Reading lists|Past exam papers|Media Hopper recordings|Careers and jobs|Internships and work experience|MyCareerHub opportunities|Careers events|University events|Students’ Association events|Registry Services",
    "zh-Hans": "MyEd 学校门户|Learn 课程与课件|EUCLID 学生记录|正式选课|个人课表|学位要求与课程目录|图书馆|阅读清单|历年试卷|Media Hopper 课程录播|就业与求职|实习与工作经验|MyCareerHub 职位信息|职业与招聘活动|学校活动|学生会与社团活动|学生事务",
    "zh-Hant": "MyEd 學校入口|Learn 課程與教材|EUCLID 學生紀錄|正式選課|個人課表|學位要求與課程目錄|圖書館|閱讀清單|歷年試卷|Media Hopper 課程錄影|就業與求職|實習與工作經驗|MyCareerHub 職位資訊|職涯與招聘活動|學校活動|學生會與社團活動|學生事務",
    "fr-FR": "Portail MyEd|Cours et supports Learn|Dossier étudiant EUCLID|Inscriptions aux cours|Emploi du temps personnel|Règlements et programmes|Bibliothèque|Listes de lecture|Annales d’examens|Enregistrements Media Hopper|Carrières et emplois|Stages et expérience professionnelle|Offres MyCareerHub|Événements professionnels|Événements universitaires|Événements de l’association étudiante|Scolarité",
    "es-ES": "Portal MyEd|Cursos y materiales Learn|Expediente del estudiante EUCLID|Matrícula en cursos|Horario personal|Normativa y programas|Biblioteca|Listas de lectura|Exámenes de años anteriores|Grabaciones Media Hopper|Carreras y empleo|Prácticas y experiencia laboral|Ofertas MyCareerHub|Eventos profesionales|Eventos universitarios|Eventos de la asociación estudiantil|Gestión académica",
    "de-DE": "MyEd Portal|Learn Kurse und Materialien|EUCLID Studierendenakte|Kursbelegungen|Persönlicher Stundenplan|Studienordnungen und Programme|Bibliothek|Leselisten|Frühere Prüfungen|Media Hopper Aufzeichnungen|Karriere und Stellen|Praktika und Berufserfahrung|MyCareerHub Angebote|Karriereveranstaltungen|Universitätsveranstaltungen|Veranstaltungen der Studierendenvertretung|Studierendenverwaltung",
    "ar": "بوابة MyEd|مقررات ومواد Learn|سجل الطالب EUCLID|المقررات المسجلة|الجدول الدراسي الشخصي|لوائح وبرامج الدرجات العلمية|المكتبة|قوائم القراءة|أوراق الامتحانات السابقة|تسجيلات Media Hopper|المسار المهني والوظائف|التدريب والخبرة العملية|فرص MyCareerHub|الفعاليات المهنية|فعاليات الجامعة|فعاليات اتحاد الطلبة|شؤون الطلاب",
    "hi": "MyEd पोर्टल|Learn पाठ्यक्रम और सामग्री|EUCLID छात्र रिकॉर्ड|पंजीकृत पाठ्यक्रम|व्यक्तिगत समय सारणी|डिग्री नियम और कार्यक्रम|पुस्तकालय|पठन सूचियाँ|पिछले परीक्षा प्रश्नपत्र|Media Hopper रिकॉर्डिंग|करियर और नौकरियाँ|इंटर्नशिप और कार्य अनुभव|MyCareerHub अवसर|करियर कार्यक्रम|विश्वविद्यालय कार्यक्रम|छात्र संघ कार्यक्रम|छात्र प्रशासन",
    "ja": "MyEd ポータル|Learn 授業と教材|EUCLID 学生記録|履修登録済み科目|個人時間割|学位規則と教育課程|図書館|リーディングリスト|過去の試験問題|Media Hopper 講義録画|キャリアと求人|インターンシップと就業体験|MyCareerHub 求人情報|キャリアイベント|大学イベント|学生自治会イベント|学務サービス",
    "ko": "MyEd 포털|Learn 강좌와 학습 자료|EUCLID 학생 기록|수강 신청 과목|개인 시간표|학위 규정과 교육과정|도서관|읽기 목록|기출 시험 문제|Media Hopper 강의 녹화|진로와 취업|인턴십과 실무 경험|MyCareerHub 채용 정보|진로 행사|대학 행사|학생회 행사|학사 행정",
}
CATALOG = {locale: dict(zip(SERVICE_IDS, titles.split("|"), strict=True)) for locale, titles in TITLES.items()}
NMR_TITLES = {"en-GB": "NMR raw data", "zh-Hans": "NMR 核磁原始数据", "zh-Hant": "NMR 核磁原始資料",
              "fr-FR": "Données RMN brutes", "es-ES": "Datos RMN originales", "de-DE": "NMR-Rohdaten",
              "ar": "بيانات الرنين المغناطيسي النووي الخام", "hi": "NMR मूल डेटा", "ja": "NMR 生データ", "ko": "NMR 원시 데이터"}
for _locale, _title in NMR_TITLES.items(): CATALOG[_locale]["nmr"] = _title
CATEGORY_KEYS = ("portal", "study", "record", "record", "study", "study", "resources", "resources",
                 "resources", "resources", "careers", "careers", "careers", "events", "events", "events", "support")
CATEGORIES = {
    "en-GB": "Portal|Study|Student record|Learning resources|Careers|Events|Student support",
    "zh-Hans": "门户|课业|学籍|学习资源|就业|活动|学生支持",
    "zh-Hant": "入口|課業|學籍|學習資源|就業|活動|學生支援",
    "fr-FR": "Portail|Études|Dossier étudiant|Ressources pédagogiques|Carrières|Événements|Accompagnement étudiant",
    "es-ES": "Portal|Estudios|Expediente académico|Recursos de aprendizaje|Empleo|Eventos|Apoyo al estudiante",
    "de-DE": "Portal|Studium|Studierendenakte|Lernressourcen|Karriere|Veranstaltungen|Studierendenberatung",
    "ar": "البوابة|الدراسة|سجل الطالب|موارد التعلم|المسار المهني|الفعاليات|دعم الطلاب",
    "hi": "पोर्टल|अध्ययन|छात्र रिकॉर्ड|अध्ययन संसाधन|करियर|कार्यक्रम|छात्र सहायता",
    "ja": "ポータル|学習|学生記録|学習資料|キャリア|イベント|学生支援",
    "ko": "포털|학업|학생 기록|학습 자료|진로|행사|학생 지원",
}
CATEGORY_LABELS = {loc: dict(zip(("portal", "study", "record", "resources", "careers", "events", "support"), text.split("|"), strict=True)) for loc, text in CATEGORIES.items()}

def normalize_locale(value):
    value = value.strip().replace("_", "-")
    if value.casefold() == "auto":
        return "auto"
    if len(value) > 63 or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value):
        raise ValueError("Use auto or a BCP 47 language tag, such as fr-FR or zh-Hant.")
    parts = value.split("-")
    return "-".join([parts[0].lower()] + [p.title() if len(p) == 4 else p.upper() if len(p) == 2 else p.lower() for p in parts[1:]])

def catalog_locale(value):
    value = normalize_locale(value)
    language = value.split("-")[0]
    if language == "zh":
        return "zh-Hant" if any(p in value.split("-") for p in ("Hant", "TW", "HK", "MO")) else "zh-Hans"
    return {"en":"en-GB", "fr":"fr-FR", "es":"es-ES", "de":"de-DE", "ar":"ar", "hi":"hi", "ja":"ja", "ko":"ko"}.get(language, "en-GB")

def validate_timezone(value):
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError("Use an IANA timezone, such as Europe/London.")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Use an IANA timezone, such as Europe/London.") from exc
    return value

def preferences(store, locale=None, display_timezone=None, bilingual_titles=None, include_languages=False):
    changes = {}
    if locale is not None:
        changes["locale"] = normalize_locale(locale)
    if display_timezone is not None:
        changes["display_timezone"] = validate_timezone(display_timezone)
    if bilingual_titles is not None:
        if not isinstance(bilingual_titles, bool):
            raise ValueError("bilingual_titles must be a boolean.")
        changes["bilingual_titles"] = bilingual_titles
    saved = store.preferences(changes)
    selected = {"locale": normalize_locale(os.environ.get("UOE_LOCALE", "auto")),
                "display_timezone": "Europe/London", "bilingual_titles": True, **saved}
    value = {"preferences": selected, "changed": bool(changes), "local_only": True,
             "presentation": presentation(store, saved=selected),
             "translation_scope": "Local service catalog; the host translates explanations. Source documents, course IDs and exact dates remain unchanged."}
    if include_languages:
        value["catalog_languages"] = LANGUAGES
        value["other_languages"] = "Accepted for host responses, with an explicit English catalog fallback."
    return value

def presentation(store, locale=None, display_timezone=None, saved=None):
    settings = store.preferences() if saved is None else saved
    requested = normalize_locale(locale if locale is not None else settings.get("locale", os.environ.get("UOE_LOCALE", "auto")))
    catalog = catalog_locale(requested)
    return {"response_language": requested, "catalog_language": catalog,
            "catalog_fallback": requested != "auto" and requested.split("-")[0] != catalog.split("-")[0],
            "display_timezone": validate_timezone(display_timezone or settings.get("display_timezone", "Europe/London")),
            "source_timezone": "Europe/London", "bilingual_titles": settings.get("bilingual_titles", True),
            "direction": "rtl" if requested.split("-")[0] in {"ar", "fa", "he", "ur"} else "ltr"}

def search_key(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)).split())

def service_labels(service_id, locale):
    code = catalog_locale(locale)
    if service_id == "nmr":
        return {"title": CATALOG[code][service_id], "official_name": CATALOG["en-GB"][service_id],
                "category": CATEGORY_LABELS[code]["resources"], "category_id": "resources"}
    index = SERVICE_IDS.index(service_id)
    return {"title": CATALOG[code][service_id], "official_name": CATALOG["en-GB"][service_id],
            "category": CATEGORY_LABELS[code][CATEGORY_KEYS[index]], "category_id": CATEGORY_KEYS[index]}

def service_aliases(service_id):
    return " ".join(catalog[service_id] for catalog in CATALOG.values())
