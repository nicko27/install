import ast
import os
import graphviz

def extract_classes_and_functions(file_path):
    """Analyse un fichier Python et extrait les classes et fonctions"""
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return [], []

    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    return classes, functions

def scan_directory(directory):
    """Parcourt un dossier et retourne les classes et fonctions trouvées"""
    structure = {}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                classes, functions = extract_classes_and_functions(file_path)
                if classes or functions:
                    structure[file_path] = {"classes": classes, "functions": functions}
    return structure

def generate_graph(structure, output_file="code_structure"):
    """Génère un graphe de la structure avec Graphviz"""
    dot = graphviz.Digraph(format="png")

    for file, elements in structure.items():
        filename = os.path.basename(file)
        dot.node(filename, shape="box", style="filled", fillcolor="lightblue")

        for cls in elements["classes"]:
            class_node = f"{filename}:{cls}"
            dot.node(class_node, shape="ellipse", style="filled", fillcolor="lightgreen")
            dot.edge(filename, class_node)

        for func in elements["functions"]:
            func_node = f"{filename}:{func}"
            dot.node(func_node, shape="ellipse", style="filled", fillcolor="lightyellow")
            dot.edge(filename, func_node)

    dot.render(output_file, view=True)

# Utilisation :
projet_path = "/media/nico/Drive/pcUtils"  # Remplace par le bon chemin
structure = scan_directory(projet_path)
generate_graph(structure)
