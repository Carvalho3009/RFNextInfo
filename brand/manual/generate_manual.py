from pathlib import Path
import shutil

from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "brand"
LOGOS = BRAND / "logos" / "png"
REFS = BRAND / "references"
OUTPUT = ROOT / "output" / "pdf" / "Karvalho-Manual-de-Marca.pdf"
BRAND_COPY = BRAND / "manual" / "Karvalho-Manual-de-Marca.pdf"

W, H = landscape(A4)

INK = HexColor("#070909")
BONE = HexColor("#F4F2EB")
GOLD = HexColor("#D4A64D")
GOLD_DARK = HexColor("#8B672F")
ACID = HexColor("#A8FF16")
CORAL = HexColor("#FF6547")
BLUE = HexColor("#63B9F3")
PURPLE = HexColor("#7659D6")
MUTED = HexColor("#A6A7A2")
PANEL = HexColor("#111515")
RULE = Color(0.83, 0.65, 0.30, alpha=0.45)


def register_fonts():
    fonts = {
        "KBody": Path(r"C:\Windows\Fonts\segoeui.ttf"),
        "KBodyBold": Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        "KDisplay": Path(r"C:\Windows\Fonts\impact.ttf"),
        "KMono": Path(r"C:\Windows\Fonts\consola.ttf"),
    }
    fallbacks = {
        "KBody": "Helvetica",
        "KBodyBold": "Helvetica-Bold",
        "KDisplay": "Helvetica-Bold",
        "KMono": "Courier",
    }
    for name, path in fonts.items():
        try:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        except Exception:
            pdfmetrics.registerFont(pdfmetrics.getFont(fallbacks[name]))


def wrap(text, font, size, width):
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if not current or pdfmetrics.stringWidth(trial, font, size) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def paragraph(c, text, x, y, width, size=12, leading=None, color=MUTED, font="KBody"):
    leading = leading or size * 1.45
    c.setFillColor(color)
    c.setFont(font, size)
    for line in wrap(text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def contain(c, path, x, y, width, height, padding=0):
    from PIL import Image
    path = Path(path)
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min((width - padding * 2) / iw, (height - padding * 2) / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(str(path), x + (width - dw) / 2, y + (height - dh) / 2, dw, dh, mask="auto")


def cover_image(c, path, x, y, width, height):
    from PIL import Image
    path = Path(path)
    with Image.open(path) as im:
        iw, ih = im.size
    scale = max(width / iw, height / ih)
    dw, dh = iw * scale, ih * scale
    c.saveState()
    clip = c.beginPath()
    clip.rect(x, y, width, height)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(str(path), x + (width - dw) / 2, y + (height - dh) / 2, dw, dh, mask="auto")
    c.restoreState()


def page_base(c, number, section, title, dark=True):
    bg = INK if dark else BONE
    fg = BONE if dark else INK
    c.setFillColor(bg)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setStrokeColor(RULE if dark else GOLD_DARK)
    c.setLineWidth(0.7)
    c.line(36, H - 34, W - 36, H - 34)
    c.setFont("KMono", 7)
    c.setFillColor(GOLD if dark else GOLD_DARK)
    c.drawString(36, H - 24, f"KARVALHO / MANUAL DE MARCA / {section.upper()}")
    c.drawRightString(W - 36, H - 24, f"{number:02d} / 12")
    c.setFillColor(fg)
    c.setFont("KDisplay", 33)
    c.drawString(36, H - 82, title.upper())
    c.setStrokeColor(RULE if dark else GOLD_DARK)
    c.line(36, 30, W - 36, 30)
    c.setFont("KMono", 7)
    c.setFillColor(MUTED if dark else HexColor("#535650"))
    c.drawString(36, 18, "VERSÃO 1.0 / JULHO 2026")
    c.drawRightString(W - 36, 18, "CLARO. CURIOSO. SEM ENROLAÇÃO.")


def pill(c, text, x, y, color=GOLD):
    width = pdfmetrics.stringWidth(text.upper(), "KMono", 7) + 18
    c.setStrokeColor(color)
    c.setFillColor(Color(color.red, color.green, color.blue, alpha=0.08))
    c.roundRect(x, y - 5, width, 19, 4, stroke=1, fill=1)
    c.setFillColor(color)
    c.setFont("KMono", 7)
    c.drawString(x + 9, y + 1, text.upper())
    return width


def page_1(c):
    c.setFillColor(INK)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    cover_image(c, REFS / "hero-atlas.png", W * 0.49, 0, W * 0.51, H)
    c.setFillColor(Color(0.027, 0.035, 0.035, alpha=0.55))
    c.rect(W * 0.42, 0, W * 0.18, H, stroke=0, fill=1)
    contain(c, LOGOS / "karvalho-primary-gold.png", 34, H - 164, 385, 122)
    c.setFillColor(BONE)
    c.setFont("KDisplay", 53)
    c.drawString(48, 260, "MANUAL DE MARCA")
    c.setFillColor(CORAL)
    c.setFont("KDisplay", 38)
    c.drawString(48, 215, "SISTEMA VISUAL 1.0")
    paragraph(c, "Identidade autoral para guias, servidores, ferramentas e projetos de jogos.", 50, 176, 330, 13, color=BONE)
    c.setStrokeColor(GOLD)
    c.line(48, 72, 390, 72)
    c.setFillColor(GOLD)
    c.setFont("KMono", 8)
    c.drawString(48, 54, "KARVALHO / 2026")
    c.drawRightString(390, 54, "PORTUGUES / ENGLISH READY")
    c.showPage()


def page_2(c):
    page_base(c, 2, "fundamentos", "Essência e posicionamento")
    c.setFillColor(CORAL)
    c.setFont("KDisplay", 46)
    c.drawString(38, 440, "JOGAR SEM")
    c.drawString(38, 392, "COMPLICAÇÃO.")
    paragraph(c, "Karvalho organiza a complexidade dos servidores de jogos em guias claros, referências confiáveis e ferramentas realmente úteis.", 40, 352, 330, 15, color=BONE)

    cards = [
        ("PROMESSA", "Ajudar pessoas a criar, entender e manter seus mundos com menos atrito.", ACID),
        ("PERSONALIDADE", "Clara, curiosa, confiável, experiente e levemente épica.", GOLD),
        ("PÚBLICO", "Jogadores, administradores iniciantes, comunidades e criadores de servidores.", BLUE),
    ]
    for i, (title, text, color) in enumerate(cards):
        x = 410
        y = 450 - i * 112
        c.setStrokeColor(color)
        c.setFillColor(PANEL)
        c.rect(x, y - 74, 390, 88, stroke=1, fill=1)
        c.setFillColor(color)
        c.setFont("KMono", 8)
        c.drawString(x + 15, y - 6, title)
        paragraph(c, text, x + 15, y - 30, 350, 11, color=BONE)

    c.setFont("KBodyBold", 10)
    c.setFillColor(GOLD)
    c.drawString(40, 92, "VOZ DA MARCA")
    c.setFont("KBody", 10)
    c.setFillColor(BONE)
    c.drawString(40, 70, "Diga: 'Configure em cinco passos.'")
    c.setFillColor(MUTED)
    c.drawString(270, 70, "Evite: 'Domine a infraestrutura definitiva de alta performance.'")
    c.showPage()


def page_3(c):
    page_base(c, 3, "logotipo", "Assinatura principal")
    c.setFillColor(PANEL)
    c.setStrokeColor(RULE)
    c.rect(40, 205, 760, 270, stroke=1, fill=1)
    contain(c, LOGOS / "karvalho-primary-gold.png", 75, 245, 690, 180)
    c.setFillColor(ACID)
    c.circle(130, 405, 4, stroke=0, fill=1)
    c.line(134, 405, 210, 445)
    c.setFont("KMono", 7)
    c.drawString(214, 445, "BRASAO: URSO + K + ESCUDO")
    c.setFillColor(CORAL)
    c.circle(505, 285, 4, stroke=0, fill=1)
    c.line(509, 285, 590, 238)
    c.setFont("KMono", 7)
    c.drawString(594, 236, "LETTERING CUSTOMIZADO")
    c.setFillColor(BONE)
    c.setFont("KBodyBold", 11)
    c.drawString(40, 164, "Conceito")
    paragraph(c, "O brasão combina proteção, comunidade e autoria. O urso comunica força e acolhimento; o K ancora reconhecimento; o lettering medieval-digital conecta fantasia, tecnologia e memória de jogos online.", 40, 143, 760, 10.5, color=MUTED)
    c.setFillColor(GOLD)
    c.setFont("KMono", 8)
    c.drawString(40, 70, "REGRA: O NOME NUNCA DEVE SER REDIGITADO. USE SEMPRE O ARQUIVO OFICIAL.")
    c.showPage()


def page_4(c):
    page_base(c, 4, "logotipo", "Variações oficiais", dark=False)
    cells = [
        (40, 300, 365, 175, INK, "PRINCIPAL HORIZONTAL", LOGOS / "karvalho-primary-gold.png"),
        (435, 300, 365, 175, INK, "SIMBOLO / AVATAR", LOGOS / "karvalho-symbol-gold.png"),
        (40, 85, 365, 175, INK, "WORDMARK", LOGOS / "karvalho-wordmark-gold.png"),
        (435, 85, 365, 175, INK, "EMPILHADA", LOGOS / "karvalho-stacked-gold.png"),
    ]
    for x, y, w, h, bg, label, path in cells:
        c.setFillColor(bg)
        c.setStrokeColor(GOLD_DARK)
        c.rect(x, y, w, h, stroke=1, fill=1)
        contain(c, path, x + 10, y + 28, w - 20, h - 38)
        c.setFillColor(GOLD)
        c.setFont("KMono", 7)
        c.drawString(x + 12, y + 11, label)
    c.showPage()


def page_5(c):
    page_base(c, 5, "logotipo", "Proteção e redução")
    c.setFillColor(PANEL)
    c.rect(40, 260, 500, 225, stroke=0, fill=1)
    contain(c, LOGOS / "karvalho-primary-gold.png", 80, 315, 420, 120)
    c.setStrokeColor(ACID)
    c.setDash(4, 3)
    c.rect(68, 290, 445, 165, stroke=1, fill=0)
    c.setDash()
    c.setFillColor(ACID)
    c.setFont("KMono", 8)
    c.drawString(70, 467, "X")
    c.drawString(518, 370, "X")
    paragraph(c, "Área livre mínima = X, onde X equivale a 1/2 da altura do K no wordmark. Nenhum texto, borda ou imagem deve invadir esse campo.", 570, 430, 225, 11, color=BONE)

    c.setFillColor(BONE)
    c.setFont("KBodyBold", 12)
    c.drawString(40, 212, "Tamanhos mínimos")
    rows = [
        ("Horizontal", "180 px digital", "45 mm impresso"),
        ("Wordmark", "140 px digital", "35 mm impresso"),
        ("Símbolo", "48 px digital", "12 mm impresso"),
    ]
    y = 178
    for name, digital, print_size in rows:
        c.setStrokeColor(RULE)
        c.line(40, y - 8, 520, y - 8)
        c.setFont("KBodyBold", 10)
        c.setFillColor(BONE)
        c.drawString(40, y, name)
        c.setFont("KMono", 8)
        c.setFillColor(ACID)
        c.drawString(190, y, digital)
        c.setFillColor(GOLD)
        c.drawString(350, y, print_size)
        y -= 38
    paragraph(c, "Abaixo do tamanho mínimo, use a versão monocromática. O acabamento dourado perde leitura em reduções extremas.", 570, 182, 225, 10.5, color=MUTED)
    c.showPage()


def page_6(c):
    page_base(c, 6, "cores", "Paleta e hierarquia")
    swatches = [
        ("CARVÃO", "#070909", "RGB 7 9 9", "CMYK 22 0 0 96", INK, BONE),
        ("OSSO", "#F4F2EB", "RGB 244 242 235", "CMYK 0 1 4 4", BONE, INK),
        ("OURO", "#D4A64D", "RGB 212 166 77", "CMYK 0 22 64 17", GOLD, INK),
        ("ÁCIDO", "#A8FF16", "RGB 168 255 22", "CMYK 34 0 91 0", ACID, INK),
        ("CORAL", "#FF6547", "RGB 255 101 71", "CMYK 0 60 72 0", CORAL, INK),
        ("ÁGUA", "#63B9F3", "RGB 99 185 243", "CMYK 59 24 0 5", BLUE, INK),
    ]
    gap = 8
    sw = (W - 80 - gap * 5) / 6
    for i, (name, hexa, rgb, cmyk, color, text_color) in enumerate(swatches):
        x = 40 + i * (sw + gap)
        c.setFillColor(color)
        c.setStrokeColor(GOLD_DARK)
        c.rect(x, 190, sw, 290, stroke=1, fill=1)
        c.setFillColor(text_color)
        c.setFont("KDisplay", 18)
        c.drawString(x + 10, 245, name)
        c.setFont("KMono", 7)
        c.drawString(x + 10, 228, hexa)
        c.drawString(x + 10, 216, rgb)
        c.drawString(x + 10, 204, cmyk)
    c.setFillColor(BONE)
    c.setFont("KBodyBold", 11)
    c.drawString(40, 148, "Proporção recomendada")
    c.setFillColor(MUTED)
    c.setFont("KBody", 10)
    c.drawString(40, 126, "70% carvão/osso  |  15% ouro  |  10% ácido  |  5% coral/água para estados e rotas.")
    c.setFillColor(CORAL)
    c.setFont("KMono", 8)
    c.drawString(40, 88, "NÃO USE TODAS AS CORES COM O MESMO PESO. O OURO ASSINA; AS CORES ELEMENTAIS ORIENTAM.")
    c.showPage()


def page_7(c):
    page_base(c, 7, "tipografia", "Sistema tipográfico")
    contain(c, LOGOS / "karvalho-wordmark-gold.png", 40, 355, 760, 110)
    c.setFillColor(GOLD)
    c.setFont("KMono", 8)
    c.drawString(40, 340, "01 / LETTERING KARVALHO - ARTE EXCLUSIVA, NÃO É UMA FONTE")

    c.setFillColor(BONE)
    c.setFont("KDisplay", 40)
    c.drawString(40, 270, "BAHNSCHRIFT CONDENSED / DISPLAY")
    c.setFillColor(MUTED)
    c.setFont("KBody", 10)
    c.drawString(40, 250, "Títulos curtos, hierarquia forte e linguagem editorial. Alternativa web: Barlow Condensed Black.")

    c.setFillColor(BONE)
    c.setFont("KBodyBold", 26)
    c.drawString(40, 185, "Inter / Segoe UI para leitura clara")
    paragraph(c, "Use peso regular em textos longos e semibold em chamadas. Evite parágrafos centralizados e linhas acima de 75 caracteres.", 40, 160, 560, 11, color=MUTED)

    c.setFillColor(ACID)
    c.setFont("KMono", 14)
    c.drawString(40, 95, "K-001  /  QUEST LOG  /  SERVER STATUS")
    c.setFillColor(MUTED)
    c.setFont("KBody", 9)
    c.drawString(40, 75, "JetBrains Mono ou Consolas para índices, versões, comandos e etiquetas funcionais.")
    c.showPage()


def page_8(c):
    page_base(c, 8, "grafismos", "Linguagem de jogo")
    cover_image(c, REFS / "guide-triptych.png", 40, 278, 760, 200)
    labels = [
        ("RUNAS E ASAS", "Transições, divisores e sinais de guilda.", GOLD),
        ("RAID E QUEST", "Hierarquia, papéis e progresso de tarefas.", CORAL),
        ("ELEMENTOS", "Rotas e categorias: natureza, fogo, água e arcano.", ACID),
        ("BESTIÁRIO", "Índices K-001 e criaturas originais como repertório.", BLUE),
    ]
    for i, (title, text, color) in enumerate(labels):
        x = 40 + (i % 2) * 390
        y = 230 - (i // 2) * 80
        c.setFillColor(color)
        c.circle(x + 7, y + 6, 5, stroke=0, fill=1)
        c.setFont("KBodyBold", 10)
        c.drawString(x + 24, y + 2, title)
        paragraph(c, text, x + 24, y - 18, 330, 9.5, color=MUTED)
    c.setFillColor(GOLD)
    c.setFont("KMono", 7)
    c.drawString(40, 64, "REFERÊNCIAS: MMORPG CLÁSSICO, GUILDAS, RAIDS E COLEÇÃO DE CRIATURAS - SEM REPRODUZIR ATIVOS DE FRANQUIAS.")
    c.showPage()


def page_9(c):
    page_base(c, 9, "imagem", "Ilustração e repertório")
    cover_image(c, REFS / "hero-atlas.png", 40, 72, 355, 410)
    cover_image(c, REFS / "bestiary-strip.png", 430, 310, 370, 172)
    c.setFillColor(BONE)
    c.setFont("KBodyBold", 11)
    c.drawString(430, 278, "Direção de arte")
    paragraph(c, "Mundos isométricos, mapas de rota, fortalezas, portais, inventários e criaturas autorais. Fundo carvão, linha dourada e cor elemental pontual. Textura rica, mas com áreas de descanso.", 430, 255, 350, 10.5, color=MUTED)
    c.setFillColor(CORAL)
    c.setFont("KBodyBold", 11)
    c.drawString(430, 160, "Limite de referência")
    paragraph(c, "Ragnarok Online, World of Warcraft e Pokémon pertencem aos seus respectivos titulares. A marca deve traduzir memória e sistemas - nunca copiar personagens, logos, nomes, interfaces ou símbolos protegidos.", 430, 137, 350, 10.5, color=BONE)
    c.showPage()


def page_10(c):
    page_base(c, 10, "composição", "Layout e aplicações")
    c.setFillColor(PANEL)
    c.setStrokeColor(RULE)
    c.roundRect(40, 80, 390, 400, 12, stroke=1, fill=1)
    cover_image(c, REFS / "approved-concept.png", 57, 98, 356, 365)
    c.setFillColor(BONE)
    c.setFont("KBodyBold", 11)
    c.drawString(470, 440, "Princípios de composição")
    principles = [
        "1. Tipografia grande + uma imagem protagonista.",
        "2. Grade assimétrica com alinhamentos rigorosos.",
        "3. Bordas finas e cantos inspirados em inventários.",
        "4. Um acento elemental por bloco, nunca todos.",
        "5. Densidade de jogo equilibrada por espaco negativo.",
    ]
    y = 405
    for item in principles:
        c.setStrokeColor(RULE)
        c.line(470, y - 8, 800, y - 8)
        c.setFillColor(BONE)
        c.setFont("KBody", 10)
        c.drawString(470, y + 5, item)
        y -= 48
    c.setFillColor(ACID)
    c.setFont("KMono", 8)
    c.drawString(470, 135, "APLICAÇÕES PRIORITÁRIAS")
    paragraph(c, "Capa de guia, miniatura, avatar, cabeçalho de projeto, material de servidor, documentação e redes sociais.", 470, 112, 320, 10.5, color=MUTED)
    c.showPage()


def page_11(c):
    page_base(c, 11, "uso", "Certo e errado", dark=False)
    c.setFillColor(INK)
    c.rect(40, 315, 365, 165, stroke=0, fill=1)
    contain(c, LOGOS / "karvalho-primary-gold.png", 55, 340, 335, 115)
    c.setFillColor(HexColor("#397B24"))
    c.setFont("KBodyBold", 10)
    c.drawString(40, 295, "CERTO / ouro sobre carvao com respiro")

    c.setFillColor(GOLD)
    c.rect(435, 315, 365, 165, stroke=0, fill=1)
    contain(c, LOGOS / "karvalho-primary-gold.png", 450, 350, 335, 90)
    c.setFillColor(CORAL)
    c.setFont("KBodyBold", 10)
    c.drawString(435, 295, "ERRADO / baixo contraste e cor concorrente")

    wrongs = [
        "Não esticar, condensar ou inclinar.",
        "Não alterar letras, espaçamento ou brasão.",
        "Não aplicar glow, sombra, contorno ou degradê extra.",
        "Não usar ouro sobre imagem detalhada sem painel de contraste.",
        "Não substituir o urso por personagem de franquia.",
        "Não misturar mais de um acento elemental por mensagem.",
    ]
    y = 235
    for i, text in enumerate(wrongs):
        x = 40 + (i % 2) * 395
        yy = y - (i // 2) * 55
        c.setFillColor(CORAL)
        c.setFont("KDisplay", 18)
        c.drawString(x, yy, "X")
        paragraph(c, text, x + 28, yy + 2, 330, 10, color=INK)
    c.showPage()


def page_12(c):
    page_base(c, 12, "entrega", "Arquivos e decisão de uso")
    c.setFillColor(BONE)
    c.setFont("KBodyBold", 13)
    c.drawString(40, 455, "Escolha rápida")
    rows = [
        ("Marca completa", "karvalho-primary-gold.png", "Fundos escuros, capas e cabecalhos"),
        ("Avatar / favicon", "karvalho-symbol-gold.png", "Perfis, ícones e espaços quadrados"),
        ("Nome isolado", "karvalho-wordmark-gold.png", "Rodapes, assinaturas e faixas"),
        ("Composição vertical", "karvalho-stacked-gold.png", "Capa, pôster e formato retrato"),
        ("Uma cor clara", "karvalho-primary-white.png", "Fundos escuros e impressão simples"),
        ("Uma cor escura", "karvalho-primary-black.png", "Fundos claros e documentos"),
    ]
    y = 418
    for name, file_name, use in rows:
        c.setStrokeColor(RULE)
        c.line(40, y - 11, 800, y - 11)
        c.setFillColor(GOLD)
        c.setFont("KBodyBold", 9)
        c.drawString(40, y, name)
        c.setFillColor(BONE)
        c.setFont("KMono", 8)
        c.drawString(190, y, file_name)
        c.setFillColor(MUTED)
        c.setFont("KBody", 9)
        c.drawString(475, y, use)
        y -= 44

    c.setFillColor(PANEL)
    c.rect(40, 76, 760, 72, stroke=0, fill=1)
    contain(c, LOGOS / "karvalho-symbol-gold.png", 48, 82, 80, 58)
    c.setFillColor(BONE)
    c.setFont("KBodyBold", 11)
    c.drawString(140, 119, "Regra final")
    c.setFillColor(MUTED)
    c.setFont("KBody", 9.5)
    c.drawString(140, 98, "Se a marca competir com o conteúdo, reduza o grafismo - nunca altere o logotipo.")
    c.showPage()


def build():
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT), pagesize=(W, H), pageCompression=1)
    c.setTitle("Karvalho - Manual de Marca")
    c.setAuthor("Karvalho")
    c.setSubject("Sistema de identidade visual, logotipo e regras de aplicação")
    for page in (page_1, page_2, page_3, page_4, page_5, page_6, page_7, page_8, page_9, page_10, page_11, page_12):
        page(c)
    c.save()
    shutil.copy2(OUTPUT, BRAND_COPY)
    print(OUTPUT)


if __name__ == "__main__":
    build()
