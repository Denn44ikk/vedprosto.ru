from __future__ import annotations

from urllib.request import urlopen
from xml.etree import ElementTree

from .models import CurrencyRate
from .models import CurrencyRatesSnapshot


class CurrencyService:
    CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

    @staticmethod
    def _parse_rate(root: ElementTree.Element, code: str) -> CurrencyRate | None:
        for node in root.findall("Valute"):
            char_code = (node.findtext("CharCode") or "").strip().upper()
            if char_code != code.upper():
                continue
            nominal_text = (node.findtext("Nominal") or "1").strip()
            value_text = (node.findtext("Value") or "").strip().replace(",", ".")
            try:
                nominal = int(float(nominal_text))
                value_rub = float(value_text)
            except ValueError:
                return None
            return CurrencyRate(code=code.upper(), nominal=nominal, value_rub=value_rub)
        return None

    def get_cbr_daily_rates(self) -> CurrencyRatesSnapshot:
        try:
            with urlopen(self.CBR_DAILY_URL, timeout=8) as response:
                payload = response.read()
        except Exception as exc:
            raise RuntimeError(f"Не удалось получить курсы ЦБ РФ: {exc}") from exc

        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise RuntimeError(f"Ответ ЦБ РФ не удалось разобрать: {exc}") from exc

        date = (root.attrib.get("Date") or "").strip()
        usd = self._parse_rate(root, "USD")
        eur = self._parse_rate(root, "EUR")
        note = f"Экосбор считаем по USD ЦБ РФ на {date}." if date else "Экосбор считаем по USD ЦБ РФ."
        return CurrencyRatesSnapshot(
            source="CBR",
            date=date,
            note=note,
            usd=usd,
            eur=eur,
        )

