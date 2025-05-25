import fitz  # PyMuPDF
import docx
import pandas as pd

def lire_fichier(fichier):
    if fichier.type == "text/plain":
        return fichier.read().decode("utf-8")
    elif fichier.type == "application/pdf":
        with fitz.open(stream=fichier.read(), filetype="pdf") as doc:
            return "\n".join([page.get_text() for page in doc])
    elif fichier.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(fichier)
        return "\n".join([para.text for para in doc.paragraphs])
    elif fichier.type == "text/csv":
        df = pd.read_csv(fichier)
        return df.to_string(index=False)
    else:
        return "Format de fichier non pris en charge."
