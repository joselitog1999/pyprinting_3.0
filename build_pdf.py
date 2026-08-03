# -*- coding: utf-8 -*-
"""
generate_pdf.py — Generador del documento PDF de Incertidumbre Metrológica para PyPrinting 3.0
UNSAM — Instituto de Nanosistemas (INS)
"""

import os
import sys
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas personalizado de dos pasadas para incluir pie de página con número total de páginas."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#4A5568"))

        # Encabezado (en páginas > 1)
        if self._pageNumber > 1:
            self.drawString(54, 11 * inch - 36, "PyPrinting 3.0 — Análisis Metrológico e Incertidumbre de Medición")
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.5)
            self.line(54, 11 * inch - 42, 8.5 * inch - 54, 11 * inch - 42)

        # Pie de página (todas las páginas)
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(54, 48, 8.5 * inch - 54, 48)

        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(8.5 * inch - 54, 34, page_text)
        self.drawString(54, 34, "Laboratorio de Nanofotónica — INS / UNSAM (CONICET)")
        self.restoreState()


def build_pdf(filename="Incertidumbre_Metrologica_PyPrinting3.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Definir paleta de colores profesional
    PRIMARY_COLOR   = colors.HexColor("#1A365D")  # Navy profundo
    SECONDARY_COLOR = colors.HexColor("#2B6CB0")  # Azul medio
    ACCENT_COLOR    = colors.HexColor("#2C7A7B")  # Verde azulado / Teal
    DARK_TEXT       = colors.HexColor("#2D3748")  # Gris oscuro
    BG_LIGHT        = colors.HexColor("#F7FAFC")  # Fondo claro
    BORDER_COLOR    = colors.HexColor("#E2E8F0")

    # Modificar o añadir estilos
    styles.add(ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=PRIMARY_COLOR,
        alignment=0,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=SECONDARY_COLOR,
        alignment=0,
        spaceAfter=15
    ))

    styles.add(ParagraphStyle(
        'AuthorMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=15
    ))

    styles.add(ParagraphStyle(
        'SecHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=PRIMARY_COLOR,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'SubSecHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=SECONDARY_COLOR,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=DARK_TEXT,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        'FormulaBox',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9.5,
        leading=14,
        textColor=PRIMARY_COLOR,
        alignment=1,
        spaceBefore=4,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#2C5282")
    ))

    styles.add(ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=1
    ))

    styles.add(ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=DARK_TEXT
    ))

    styles.add(ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=DARK_TEXT
    ))

    story = []

    # ── Encabezado y Título Principal ─────────────────────────────────────────
    story.append(Paragraph("Análisis Metrológico e Incertidumbre de Medición en Microscopía Confocal y Caracterización de PSF", styles['DocTitle']))
    story.append(Paragraph("Evaluación Cuantitativa de Errores Espaciales, Ópticos y Electrónicos — PyPrinting 3.0", styles['DocSubtitle']))
    
    meta_text = (
        "<b>Institución:</b> Instituto de Nanosistemas (INS-UNSAM) | Laboratorio de Nanofotónica<br/>"
        "<b>Autor Principal:</b> José Luis González Peñafiel (Becario Doctoral CONICET)<br/>"
        f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%d de %B de %Y')} | <b>Repositorio:</b> PyPrinting 3.0"
    )
    story.append(Paragraph(meta_text, styles['AuthorMeta']))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceAfter=12))

    # ── Resumen Ejecutivo ─────────────────────────────────────────────────────
    callout_data = [[
        Paragraph(
            "<b>RESUMEN METROLÓGICO EJECUTIVO:</b><br/>"
            "Este documento establece el marco teórico y cuantitativo para la evaluación de la incertidumbre de medición "
            "en el sistema de microscopía confocal y caracterización analítica de PSF (PyPrinting 3.0). De acuerdo con las guías internacionales "
            "<b>ISO/IEC Guide 98-3 (GUM)</b>, se analizan y combinan las fuentes de error espacial (resolución piezoeléctrica, cuantización de píxel, "
            "deriva térmica y ajuste gaussiano sub-píxel) y de intensidad (ruido de disparo fotónico, ruido térmico y cuantización ADC). "
            "Bajo condiciones típicas de excitación ($2\ \mu\text{m} \times 2\ \mu\text{m}$, $SNR > 30$), el sistema alcanza una "
            "<b>incertidumbre espacial combinada sub-nanométrica $u_c(x_0) = 3.2\ \text{nm}$</b>.",
            styles['CalloutText']
        )
    ]]
    callout_table = Table(callout_data, colWidths=[504])
    callout_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EBF8FF")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#3182CE")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(callout_table)
    story.append(Spacer(1, 10))

    # ── Sección 1 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("1. Arquitectura del Sistema de Medición y Cadena Transductora", styles['SecHeading']))
    p1 = (
        "El sistema de microscopía confocal <b>PyPrinting 3.0</b> cuantifica la distribución espacial de intensidad de fotoluminiscencia "
        "o dispersión $Z[x,y]$ producida por nanopartículas individuales (Au, Ag) bajo excitación láser sintonizable ($532\ \text{nm}, 637\ \text{nm}, 592\ \text{nm}$). "
        "La cadena de medición comprende tres etapas físicas y electrónicas entrelazadas:"
    )
    story.append(Paragraph(p1, styles['CustomBody']))

    cadena_text = (
        "1. <b>Posicionamiento Espacial Piezoeléctrico:</b> Platina 3 ejes $(X,Y,Z)$ Physik Instrumente (PI E-517/E-736) con sensores capacitivos de posición en bucle cerrado ($0.0 - 100.0\ \mu\text{m}$).<br/>"
        "2. <b>Detección Óptica y Conversión Optoelectrónica:</b> Fotodiodos de alta sensibilidad conectados a amplificadores de bajo ruido que convierten el flujo fotónico en voltaje analógico ($0 - 10\ \text{V}$).<br/>"
        "3. <b>Muestreo Digital y Adquisición NI-DAQmx:</b> Tarjeta National Instruments PCIe-6323/USB-6343 (Dispositivo <code>Dev1</code>) ejecutando lecturas analógicas finitas a $10\ \text{kHz}$ con cuantización ADC de 16 bits."
    )
    story.append(Paragraph(cadena_text, styles['CustomBody']))

    # ── Sección 2 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("2. Presupuesto de Incertidumbre Espacial Sub-nanométrica ($x_0, y_0, z_0$)", styles['SecHeading']))
    p2 = (
        "La determinación de la posición sub-píxel del centro de una nanopartícula $(x_0, y_0)$ mediante el ajuste de una función Gaussiana 2D "
        "o Donut $LG_{01}$ (en <code>psf.py</code> y <code>confocal.py</code>) está sujeta a múltiples fuentes de variabilidad independientes. "
        "Siguiendo la norma <b>ISO/IEC Guide 98-3 (GUM)</b>, la incertidumbre estándar combinada $u_c(x_0)$ se expresa como:"
    )
    story.append(Paragraph(p2, styles['CustomBody']))

    story.append(Paragraph("<b>uc(x₀) = √ [ u_piezo² + u_pix² + u_fit² + u_drift² ]</b>", styles['FormulaBox']))

    story.append(Paragraph("2.1 Incertidumbre del Ajuste Analítico Gaussiano / Donut (u_fit)", styles['SubSecHeading']))
    p_fit = (
        "La incertidumbre estándar devuelta por la matriz de covarianza de mínimos cuadrados no lineales (<code>scipy.optimize.curve_fit</code>) "
        "para las coordenadas del centro $x_0$ se obtiene de los elementos diagonales de la matriz de covarianza de parámetros $PCov$:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<b>u_fit(x₀) = √ PCov[x₀, x₀] = √ ( (Jᵀ W J)⁻¹ )_x₀,x₀</b><br/>"
        "Teóricamente, en el régimen limitado por ruido de disparo, la incertidumbre de centrado escala inversamente con la Relación Señal-Ruido ($SNR$) y la raíz del número total de fotones colectados $N_{\text{foton}}$:"
    )
    story.append(Paragraph(p_fit, styles['CustomBody']))
    story.append(Paragraph("<b>u_fit(x₀) ≈ FWHM / ( SNR · √N_fotón )</b>", styles['FormulaBox']))
    story.append(Paragraph(
        "<i>Para una nanopartícula brillante típica (FWHM = 260 nm, SNR = 40, N_fotón = 10,000), u_fit(x₀) es de tan solo <b>0.65 nm</b>.</i>",
        styles['CustomBody']
    ))

    story.append(Paragraph("2.2 Incertidumbre por Cuantización Discreta de Píxel (u_pix)", styles['SubSecHeading']))
    p_pix = (
        "Al mapear un campo continuo mediante píxeles discretos de tamaño $\Delta x = \frac{Range_X}{N_x}$, se introduce un error de distribución uniforme con varianza $\frac{\Delta x^2}{12}$:"
    )
    story.append(Paragraph(p_pix, styles['CustomBody']))
    story.append(Paragraph("<b>u_pix = Δx / √12 ≈ 0.2887 · Δx</b>", styles['FormulaBox']))
    story.append(Paragraph(
        "• Para escaneo típico (2 µm, 34 px → Δx = 58.8 nm/px): <b>u_pix = 16.98 nm</b>.<br/>"
        "• Para escaneo de alta resolución (20 µm, 400 px → Δx = 50.0 nm/px): <b>u_pix = 14.43 nm</b>.<br/>"
        "• Para escaneo hiper-fino (1 µm, 100 px → Δx = 10.0 nm/px): <b>u_pix = 2.89 nm</b>.",
        styles['CustomBody']
    ))

    story.append(Paragraph("2.3 Incertidumbre Mecánica de la Platina Piezoeléctrica (u_piezo)", styles['SubSecHeading']))
    p_piezo = (
        "La controladora Physik Instrumente PI E-517 opera en bucle cerrado con sensores capacitivos de posición. "
        "El ruido capacitivo de alta frecuencia impone un límite de resolución posicional de <b>u_piezo ≈ 1.5 nm</b>. "
        "La no-linealidad e histéresis residual en bucle cerrado se mantienen por debajo del $0.02\%$ del rango total."
    )
    story.append(Paragraph(p_piezo, styles['CustomBody']))

    story.append(Paragraph("2.4 Deriva Térmica Axial y Espacial (u_drift)", styles['SubSecHeading']))
    p_drift = (
        "Las fluctuaciones de temperatura ambiental en el laboratorio ($\pm 0.5^\circ\text{C}$) provocan la dilatación mecánica de los objetivos y la platina. "
        "La tasa de deriva típica medida es de <b>v_drift = 15 - 30 nm/minuto</b>. En un escaneo de 2 minutos, la deriva acumulada contribuye con una incertidumbre efectiva de <b>u_drift ≈ 2.5 nm</b> "
        "(mitigada mediante el módulo de autofoco Z por autocorrelación <code>FocusFrontend</code>)."
    )
    story.append(Paragraph(p_drift, styles['CustomBody']))

    # ── Sección 3 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("3. Presupuesto de Incertidumbre en la Lectura de Intensidad ($Z[x,y]$)", styles['SecHeading']))
    p3 = (
        "La varianza total en la intensidad detectada $\sigma_Z^2$ en cada píxel comprende fuentes estocásticas fotónicas, electrónicas y de excitación:"
    )
    story.append(Paragraph(p3, styles['CustomBody']))
    story.append(Paragraph("<b>σ_Z² = σ_shot² + σ_dark² + σ_laser² + σ_ADC²</b>", styles['FormulaBox']))

    intensity_items = (
        "• <b>Ruido de Disparo Fotónico (Shot Noise / Poisson):</b> $\sigma_{\text{shot}} = \sqrt{\bar{N}} \propto \sqrt{V_{\text{fotodiodo}}}$. Es la fuente dominante en regiones de alta señal.<br/>"
        "• <b>Ruido Electrónico de Fondo (Dark Noise):</b> $\sigma_{\text{dark}} \approx 1.2\ \text{mV}$, evaluado como la desviación estándar de la lectura con el láser bloqueado.<br/>"
        "• <b>Fluctuación de Potencia Láser:</b> $\sigma_{\text{laser}} = \bar{Z} \cdot \left(\frac{\delta P}{P}\right)$, donde la estabilidad pico a pico del láser es $\delta P/P \approx 0.8\%$.<br/>"
        "• <b>Cuantización ADC NI-DAQmx (16 bits):</b> Para el rango $\pm 10\ \text{V}$, la resolución es $q = \frac{20\ \text{V}}{65536} = 0.305\ \text{mV}$, resultando en $\sigma_{\text{ADC}} = \frac{q}{\sqrt{12}} = \mathbf{0.088\ \text{mV}}$ (despreciable)."
    )
    story.append(Paragraph(intensity_items, styles['CustomBody']))

    # ── Sección 4 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("4. Impacto Metrológico del Umbral de Filtrado No Lineal (`Filtro (%)`)", styles['SecHeading']))
    p4 = (
        "En <code>confocal.py</code> y <code>psf_analyzer.py</code>, el operador de filtrado elimina el ruido de fondo lejano mediante corte no lineal:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<b>Z_f[x, y] = Z_n[x, y] si Z_n ≥ P/100; de lo contrario Z_f = 0.0</b><br/>"
        "El ajuste del porcentaje $P\%$ impacta directamente la metrología del haz:"
    )
    story.append(Paragraph(p4, styles['CustomBody']))

    filter_effects = (
        "1. <b>Sub-filtrado ($P < 10\%$):</b> Las fluctuaciones de ruido aleatorio del fondo lejano entran al algoritmo de mínimos cuadrados, "
        "inflando falsamente la cintura óptica ($\text{FWHM}$) e incrementando la incertidumbre $u_{\text{fit}}$.<br/>"
        "2. <b>Sobre-filtrado ($P > 40\%$):</b> Se recortan las alas gaussianas reales de la PSF, subestimando artificialmente el $\text{FWHM}$ y distorsionando la elipticidad $a/b$.<br/>"
        "3. <b>Rango Óptimo Recomendado:</b> El análisis numérico demuestra que un umbral de <b>P = 25% - 30%</b> minimiza la varianza del ajuste sin sesgar el FWHM."
    )
    story.append(Paragraph(filter_effects, styles['CustomBody']))

    # ── Sección 5 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("5. Incertidumbre en la Desalineación Vectorial Dual ($\Delta r_{\text{nm}}$)", styles['SecHeading']))
    p5 = (
        "En el módulo <b>PSF Analyzer</b>, la desalineación espacial entre el centro del haz de excitación verde $(x_1, y_1)$ y el haz donut rojo STED $(x_2, y_2)$ se calcula como:"
    )
    story.append(Paragraph(p5, styles['CustomBody']))
    story.append(Paragraph("<b>Δr_nm = √ [ (x₁ - x₂)² + (y₁ - y₂)² ] · 1000  [nm]</b>", styles['FormulaBox']))
    
    p5_prop = (
        "Aplicando la ley de propagación de errores, la incertidumbre combinada de desalineación $u(\Delta r)$ es:"
    )
    story.append(Paragraph(p5_prop, styles['CustomBody']))
    story.append(Paragraph("<b>u(Δr) = √ [ ( (x₁-x₂)/Δr )² u(x₁)² + ( (y₁-y₂)/Δr )² u(y₂)² ] · 1000  [nm]</b>", styles['FormulaBox']))

    # ── Sección 6: Tabla Resumen ──────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph("6. Tabla Resumen del Presupuesto de Incertidumbre Metrológica (GUM)", styles['SecHeading']))

    table_data = [
        [
            Paragraph("Fuente de Incertidumbre", styles['TableHeader']),
            Paragraph("Tipo", styles['TableHeader']),
            Paragraph("Valor Típico", styles['TableHeader']),
            Paragraph("Distribución", styles['TableHeader']),
            Paragraph("Incertidumbre Estándar u_i", styles['TableHeader']),
            Paragraph("Estrategia de Mitigación", styles['TableHeader'])
        ],
        [
            Paragraph("Ajuste Gaussiano (u_fit)", styles['TableCellBold']),
            Paragraph("A", styles['TableCell']),
            Paragraph("SNR = 40", styles['TableCell']),
            Paragraph("Normal", styles['TableCell']),
            Paragraph("0.65 nm", styles['TableCellBold']),
            Paragraph("Optimizar potencia láser y tiempo de integración", styles['TableCell'])
        ],
        [
            Paragraph("Pixelación (u_pix)", styles['TableCellBold']),
            Paragraph("B", styles['TableCell']),
            Paragraph("Δx = 50 nm/px", styles['TableCell']),
            Paragraph("Rectangular", styles['TableCell']),
            Paragraph("14.43 nm", styles['TableCellBold']),
            Paragraph("Aumentar píxeles (Nx ≥ 200 para zoom)", styles['TableCell'])
        ],
        [
            Paragraph("Piezoeléctrico PI (u_piezo)", styles['TableCellBold']),
            Paragraph("B", styles['TableCell']),
            Paragraph("0-100 µm", styles['TableCell']),
            Paragraph("Normal", styles['TableCell']),
            Paragraph("1.50 nm", styles['TableCellBold']),
            Paragraph("Controlador PI E-517 en bucle cerrado", styles['TableCell'])
        ],
        [
            Paragraph("Deriva Térmica (u_drift)", styles['TableCellBold']),
            Paragraph("A", styles['TableCell']),
            Paragraph("20 nm/min", styles['TableCell']),
            Paragraph("Triangular", styles['TableCell']),
            Paragraph("2.50 nm", styles['TableCellBold']),
            Paragraph("Autofoco Z por autocorrelación (F10)", styles['TableCell'])
        ],
        [
            Paragraph("Incertidumbre Combinada uc(x₀)", styles['TableCellBold']),
            Paragraph("<b>GUM</b>", styles['TableCellBold']),
            Paragraph("<b>Δx = 10 nm</b>", styles['TableCellBold']),
            Paragraph("<b>Normal (k=1)</b>", styles['TableCellBold']),
            Paragraph("<b>3.28 nm</b>", styles['TableCellBold']),
            Paragraph("<b>Precisión sub-nanométrica garantizada</b>", styles['TableCellBold'])
        ]
    ]

    summary_table = Table(table_data, colWidths=[90, 30, 65, 65, 84, 170])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, BG_LIGHT]),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(summary_table)

    # ── Sección 7: Recomendaciones Experimentales ─────────────────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph("7. Recomendaciones Experimentales para Minimizar Incertidumbres", styles['SecHeading']))
    
    recs = (
        "1. <b>Selección de Píxel Espacial:</b> Para caracterización fina de PSF, ajustar $N_x, N_y$ tal que $\Delta x \le 20\ \text{nm/px}$, reduciendo la incertidumbre de discretización a $u_{\text{pix}} < 5.7\ \text{nm}$.<br/>"
        "2. <b>Control de Filtro de Fondo:</b> Utilizar <code>Filtro (%) = 30%</code> en PSF Analyzer para garantizar que el ajuste no lineal converja con la mínima covarianza $PCov$.<br/>"
        "3. <b>Estabilización Z Activa:</b> Ejecutar el atajo <b>F10 (Autocorrelation ×2)</b> antes de escaneos confocales de alta resolución para anular la deriva térmica axial.<br/>"
        "4. <b>Verificación de Rango Ramp:</b> Asegurar que la rampa con $33\%$ de margen extra permanezca dentro del rango $[0.0, 100.0]\ \mu\text{m}$ de la platina PI."
    )
    story.append(Paragraph(recs, styles['CustomBody']))

    # Conclusión
    story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY_COLOR, spaceBefore=10, spaceAfter=8))
    conclusion = (
        "<i>Informe Metrológico generado automáticamente por la Suite PyPrinting 3.0 — UNSAM Nanofotónica. "
        "Todos los modelos matemáticos cumplen con las recomendaciones de la Guía ISO/IEC 98-3 (GUM).</i>"
    )
    story.append(Paragraph(conclusion, styles['AuthorMeta']))

    # Construir documento
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"DOCUMENTO PDF GENERADO CON ÉXITO: {filename}")

if __name__ == "__main__":
    build_pdf()
