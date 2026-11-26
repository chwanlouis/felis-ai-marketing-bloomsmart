from io import BytesIO
from decimal import Decimal, InvalidOperation
import logging
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
from xml.sax.saxutils import escape

from botocore.exceptions import BotoCoreError, ClientError
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from tools.env_handler import environment_handler
from tools.s3_client import s3_client


_STATIC_PATH = Path(__file__).resolve().parents[1] / "static"
_ICON_PATH = _STATIC_PATH / "bloomsmart_icon.png"
_FONT_NAME = "STSong-Light"
logger = logging.getLogger(__name__)
pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NAME))


def _text(value: Any) -> str:
    return escape(str(value or "").strip())


def _header_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    width, height = A4
    if _ICON_PATH.exists():
        canvas.drawImage(
            str(_ICON_PATH),
            18 * mm,
            height - 31 * mm,
            width=18 * mm,
            height=18 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
    canvas.setFont(_FONT_NAME, 13)
    canvas.setFillColor(colors.HexColor("#b91c1c"))
    canvas.drawString(40 * mm, height - 20 * mm, "成俊食品有限公司")
    canvas.setFont(_FONT_NAME, 9)
    canvas.setFillColor(colors.HexColor("#374151"))
    canvas.drawRightString(width - 18 * mm, height - 20 * mm, "落單 6077 6567")
    canvas.setStrokeColor(colors.HexColor("#b91c1c"))
    canvas.line(18 * mm, height - 34 * mm, width - 18 * mm, height - 34 * mm)
    canvas.setFont(_FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawCentredString(width / 2, 10 * mm, f"第 {document.page} 頁")
    canvas.restoreState()


def _product_image(
    product: dict[str, Any],
    width: float,
    height: float,
    placeholder_style: ParagraphStyle,
) -> Flowable:
    photo_url = str(product.get("photo_url", "") or "").split("|")[0].strip()
    if not photo_url:
        return Paragraph("暫無圖片", placeholder_style)

    try:
        parsed_url = urlparse(photo_url)
        bucket_name = environment_handler.S3_BUCKET_NAME
        s3_host_prefix = f"{bucket_name}.s3."
        if parsed_url.netloc.startswith(s3_host_prefix):
            image_data = s3_client.get_object(
                Bucket=bucket_name,
                Key=unquote(parsed_url.path.lstrip("/")),
            )["Body"].read()
        else:
            with urlopen(photo_url, timeout=3) as response:
                image_data = response.read()
        image_reader = ImageReader(BytesIO(image_data))
        image_width, image_height = image_reader.getSize()
        scale = min(width / image_width, height / image_height)
        return Image(
            BytesIO(image_data),
            width=image_width * scale,
            height=image_height * scale,
            hAlign="CENTER",
        )
    except (
        BotoCoreError,
        ClientError,
        HTTPError,
        URLError,
        OSError,
        ValueError,
    ) as exc:
        logger.warning("Unable to load product photo: url=%s error=%s", photo_url, exc)
        return Paragraph("暫無圖片", placeholder_style)


def build_product_catalog_pdf(
    products: Sequence[dict[str, Any]],
    product_type: str,
) -> bytes:
    if not _ICON_PATH.exists():
        raise FileNotFoundError(f"PDF icon file not found: {_ICON_PATH}")

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=42 * mm,
        bottomMargin=18 * mm,
        title=f"產品目錄 - {product_type}",
        author="成俊食品有限公司",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CatalogTitle",
        parent=styles["Title"],
        fontName=_FONT_NAME,
        fontSize=19,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#991b1b"),
        spaceAfter=5 * mm,
    )
    subtitle_style = ParagraphStyle(
        "CatalogSubtitle",
        parent=styles["Normal"],
        fontName=_FONT_NAME,
        fontSize=9,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=7 * mm,
    )
    cell_style = ParagraphStyle(
        "CatalogCell",
        parent=styles["Normal"],
        fontName=_FONT_NAME,
        fontSize=9,
        leading=13,
        alignment=TA_LEFT,
    )
    price_style = ParagraphStyle(
        "CatalogPrice",
        parent=cell_style,
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#b91c1c"),
    )
    description_style = ParagraphStyle(
        "CatalogDescription",
        parent=cell_style,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#4b5563"),
    )
    placeholder_style = ParagraphStyle(
        "CatalogImagePlaceholder",
        parent=cell_style,
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#9ca3af"),
    )

    story: list[Flowable] = [
        Spacer(1, 2 * mm),
        Paragraph(
            f"{_text(product_type)} 目錄 Catalog"
            if product_type != "all"
            else "產品目錄 Catalog",
            title_style,
        ),
        Paragraph(
            "本店提供多款不同的肉類、海產及適合寵物之食材（人類食用級），"
            "大部份均為無激素產品。",
            subtitle_style,
        ),
    ]

    page_width = A4[0] - document.leftMargin - document.rightMargin
    card_gap = 4 * mm
    card_width = (page_width - (card_gap * 2)) / 3
    card_rows: list[list[Table]] = []
    current_row: list[Table] = []
    for product in products:
        try:
            price = f"{Decimal(str(product.get('price', 0))).quantize(Decimal('0.01')):.2f}"
        except (InvalidOperation, TypeError, ValueError):
            price = "0.00"
        chinese_name = _text(product.get("cn_name") or product.get("en_name"))
        english_name = _text(product.get("en_name"))
        name = f"<b>{chinese_name}</b>"
        if english_name:
            name += f"<br/><font size='8'>{english_name}</font>"
        card_content: list[list[Flowable]] = [
            [
                _product_image(
                    product,
                    width=card_width - 12 * mm,
                    height=38 * mm,
                    placeholder_style=placeholder_style,
                )
            ],
            [Paragraph(name, cell_style)],
            [Paragraph(f"${price} / {_text(product.get('unit'))}", price_style)],
        ]
        description = _text(product.get("product_description"))
        if description:
            card_content.append([Paragraph(description, description_style)])
        card = Table(card_content, colWidths=[card_width - 4 * mm])
        card.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d1d5db")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffafa")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        current_row.append(card)
        if len(current_row) == 3:
            card_rows.append(current_row)
            current_row = []
    if current_row:
        current_row.extend(
            Table([[""]], colWidths=[card_width - 4 * mm])
            for _ in range(3 - len(current_row))
        )
        card_rows.append(current_row)

    cards_table = Table(
        card_rows,
        colWidths=[card_width] * 3,
        hAlign="LEFT",
    )
    cards_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), card_gap),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), card_gap),
            ]
        )
    )
    if card_rows:
        story.append(cards_table)
    else:
        story.append(Paragraph("此分類暫無產品。", cell_style))
    document.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buffer.getvalue()
