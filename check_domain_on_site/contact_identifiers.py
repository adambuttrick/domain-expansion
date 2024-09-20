import re

contact_identifiers = [
    # English
    "contact", "contact us",
    # French
    "contact", "contactez-nous",
    # Spanish
    "contacto", "contáctenos", "contacta con nosotros",
    # Portuguese
    "contato", "fale conosco", "contate-nos",
    # Italian
    "contatto", "contattaci",
    # German
    "kontakt", "kontaktieren sie uns", "kontaktiere uns",
    # Dutch
    "contact", "neem contact op",
    # Swedish
    "kontakt", "kontakta oss", "ta kontakt",
    # Norwegian
    "kontakt", "kontakt oss", "ta kontakt",
    # Danish
    "kontakt", "kontakt os",
    # Finnish
    "ota yhteyttä",
    # Russian
    "контакт", "контакты", "связаться с нами",
    # Polish
    "kontakt", "skontaktuj się z nami",
    # Czech
    "kontakt", "kontaktujte nás",
    # Slovak
    "kontakt", "kontaktujte nás",
    # Hungarian
    "kapcsolat", "lépjen kapcsolatba velünk",
    # Romanian
    "contact", "contactați-ne",
    # Bulgarian
    "контакт", "свържете се с нас",
    # Greek
    "επικοινωνία", "επικοινωνήστε μαζί μας",
    # Turkish
    "iletişim", "bize ulaşın",
    # Arabic
    "اتصل بنا", "تواصل معنا", "اتصال",
    # Hebrew
    "צור קשר",
    # Persian
    "تماس با ما",
    # Hindi
    "संपर्क करें", "हमसे संपर्क करें",
    # Urdu
    "ہم سے رابطہ کریں",
    # Chinese Simplified
    "联系我们",
    # Chinese Traditional
    "聯繫我們",
    # Japanese
    "お問い合わせ", "連絡先",
    # Korean
    "연락처", "문의하기",
    # Thai
    "ติดต่อเรา",
    # Vietnamese
    "liên hệ",
    # Indonesian and Malay
    "kontak", "hubungi kami",
    # Filipino/Tagalog
    "makipag-ugnayan sa amin", "kontakin kami",
    # Swahili
    "wasiliana nasi",
    # Amharic
    "ያግኙን",
    # Yoruba
    "kan si wa",
    # Zulu
    "xhumana nathi",
    # Afrikaans
    "kontak", "kontak ons",
    # Estonian
    "kontakt", "võtke meiega ühendust",
    # Latvian
    "kontakts", "sazinieties ar mums",
    # Lithuanian
    "kontaktai", "susisiekite su mumis",
    # Slovenian
    "kontakt", "kontaktirajte nas",
    # Croatian
    "kontakt", "kontaktirajte nas",
    # Serbian
    "контакт", "контактирајте нас",
    # Bosnian
    "kontakt", "kontaktirajte nas",
    # Albanian
    "kontakt", "na kontaktoni",
    # Macedonian
    "контакт", "контактирајте не",
    # Icelandic
    "hafðu samband",
    # Irish Gaelic
    "teagmháil", "déan teagmháil linn",
    # Welsh
    "cysylltu", "cysylltwch â ni",
    # Basque
    "kontaktua", "jarri gurekin harremanetan",
    # Catalan
    "contacte", "contacta'ns",
    # Galician
    "contacto", "contacta connosco",
    # Gujarati
    "અમારો સંપર્ક કરો",
    # Marathi
    "आमच्याशी संपर्क करा",
    # Punjabi
    "ਸਾਡੇ ਨਾਲ ਸੰਪਰਕ ਕਰੋ",
    # Tamil
    "எங்களை தொடர்பு கொள்ளவும்",
    # Telugu
    "మమ్మల్ని సంప్రదించండి",
    # Kannada
    "ನಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಿ",
    # Malayalam
    "ഞങ്ങളെ ബന്ധപ്പെടുക",
    # Bengali
    "যোগাযোগ করুন",
    # Nepali
    "हामीलाई सम्पर्क गर्नुहोस्",
    # Haitian Creole
    "kontakte nou",
    # Lao
    "ຕິດຕໍ່ພວກເຮົາ",
    # Khmer
    "ទាក់ទងមកពួកយើង",
    # Mongolian
    "бидэнтэй холбоо бариарай",
    # Ukrainian
    "контакти", "зв'яжіться з нами",
    # Kazakh
    "байланыс", "бізбен хабарласыңыз",
    # Uzbek
    "aloqa", "biz bilan bog'laning",
    # Azerbaijani
    "əlaqə", "bizimlə əlaqə saxlayın",
    # Georgian
    "კონტაქტი", "დაგვიკავშირდით",
    # Armenian
    "կապ", "կապվեք մեզ հետ",
    # Belarusian
    "кантакт", "звяжыцеся з намі",
    # Sinhala
    "අප අමතන්න",
    # Burmese
    "ကျွန်ုပ်တို့ကိုဆက်သွယ်ပါ",
    # Tagalog (duplicate for safety)
    "makipag-ugnayan sa amin",
]

# Compile the regex pattern
CONTACT_PATTERN = re.compile("|".join(re.escape(word) for word in contact_identifiers), re.IGNORECASE)