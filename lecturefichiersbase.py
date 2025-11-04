import io
import fitz  # PyMuPDF
import docx
import pandas as pd

PDF_MAX_PAGES_DEFAULT = 10


# ======================================================
# 🔧 Fonctions de lecture depuis des données binaires
# ======================================================

def lire_txt_bytes(data: bytes, encoding: str = "utf-8") -> str:
    """Lit un fichier texte brut à partir de bytes."""
    try:
        return data.decode(encoding, errors="ignore")
    except Exception:
        return data.decode("utf-8", errors="ignore")


def lire_pdf_bytes(data: bytes, max_pages: int = PDF_MAX_PAGES_DEFAULT) -> str:
    """Extrait le texte d’un PDF (limité en nombre de pages)."""
    with fitz.open(stream=data, filetype="pdf") as doc:
        pages = min(len(doc), max_pages) if (isinstance(max_pages, int) and max_pages > 0) else len(doc)
        textes = []
        for i in range(pages):
            try:
                textes.append(doc[i].get_text())
            except Exception:
                pass
        out = "\n".join(textes)
        if pages < len(doc):
            out += f"\n\n---\n[Texte tronqué : {pages} / {len(doc)} pages affichées]"
        return out.strip()


def lire_docx_bytes(data: bytes) -> str:
    """Extrait le texte d’un fichier DOCX."""
    f = io.BytesIO(data)
    document = docx.Document(f)
    return "\n".join(p.text for p in document.paragraphs)


def lire_csv_bytes(data: bytes, limit_rows: int = 50) -> str:
    """Lit les premières lignes d’un CSV."""
    f = io.BytesIO(data)
    try:
        df = pd.read_csv(f, nrows=limit_rows)
    except Exception:
        f.seek(0)
        df = pd.read_csv(f, sep=";", nrows=limit_rows)
    out = df.to_string(index=False)
    if len(df) == limit_rows:
        out += f"\n\n---\n[Affichage partiel : premières {limit_rows} lignes]"
    return out


# ======================================================
# 🔄 Compatibilité avec les fichiers uploadés (local)
# ======================================================

def lire_fichier(fichier):
    """Lit un fichier uploadé via Streamlit et renvoie son texte."""
    if fichier.type == "text/plain":
        return fichier.read().decode("utf-8")
    elif fichier.type == "application/pdf":
        return lire_pdf_bytes(fichier.read())
    elif fichier.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return lire_docx_bytes(fichier.read())
    elif fichier.type == "text/csv":
        return lire_csv_bytes(fichier.read())
    else:
        return "Format de fichier non pris en charge."
