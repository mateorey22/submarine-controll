from flask import Flask, jsonify, render_template

app = Flask(__name__)

# Route pour la page d'accueil (sert index.html)
@app.route("/")
def index():
    return render_template("index.html")

# Route API pour le test
@app.route("/api/test")
def api_test():
    return jsonify({"message": "L'API fonctionne!"})

# (Plus tard, tu ajouteras ici les routes pour contrôler les GPIO)
# Exemple (NE PAS UTILISER TEL QUEL avec les GPIO sans précautions) :
# @app.route("/api/gpio/<int:pin>/<int:state>")
# def control_gpio(pin, state):
#     # ... Code pour contrôler le GPIO ...
#     return jsonify({"status": "OK"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)  # 0.0.0.0 pour écouter sur toutes les interfaces
