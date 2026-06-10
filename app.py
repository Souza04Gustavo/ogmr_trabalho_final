from flask import Flask, render_template, request, jsonify
import psycopg2
import subprocess

app = Flask(__name__)

# Configurações do seu banco Postgres
DB_HOST = "localhost"
DB_NAME = "projeto_ogmr"
DB_USER = "postgres"
DB_PASS = "postgres"

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

def checar_status_porta(ip, porta):
    try:
        # Vamos usar o nome exato da MIB que testamos antes e funcionou perfeitamente
        oid = f"IF-MIB::ifAdminStatus.{porta}"
        
        resultado = subprocess.run(
            ["snmpget", "-v2c", "-c", "public", "-Oqv", ip, oid],
            capture_output=True, text=True, timeout=2
        )
        
        saida = resultado.stdout.strip().lower()
        erro = resultado.stderr.strip()
        
        # Isso vai imprimir no terminal do VS Code exatamente o que o Linux respondeu!
        print(f"DEBUG Porta {porta} -> SAIDA: '{saida}' | ERRO: '{erro}'")
        
        if "1" in saida or "up" in saida:
            return "Liberada"
        elif "2" in saida or "down" in saida:
            return "Bloqueada"
            
        return "Erro ao ler"
    except Exception as e:
        print(f"DEBUG EXCEÇÃO Porta {porta} -> {str(e)}")
        return "Erro ao ler"

@app.route('/')
def index():
    conn = get_db_connection()
    cur = conn.cursor()
    # Pega todas as máquinas e cruza com a tabela de salas e switches
    cur.execute("""
        SELECT m.id, m.nome_host, m.ip_address, m.mac_address, m.porta_ifindex, m.tipo, s.nome as sala_nome, sw.ip_address as switch_ip
        FROM maquinas m
        JOIN salas s ON m.sala_id = s.id
        JOIN switches sw ON m.switch_id = sw.id
        ORDER BY m.id;
    """)
    linhas_db = cur.fetchall()
    cur.close()
    conn.close()
    
    maquinas = []
    for m in linhas_db:
        ip_switch = m[7]
        porta = m[4]
        status_atual = checar_status_porta(ip_switch, porta)
        
        # Convertendo a tupla do banco em lista para podermos adicionar o status no final
        m_lista = list(m)
        m_lista.append(status_atual) # Vai ficar no índice 9
        maquinas.append(m_lista)
    
    return render_template('index.html', maquinas=maquinas)

@app.route('/alterar_status', methods=['POST'])
def alterar_status():
    data = request.json
    porta = data.get('porta')
    acao = data.get('acao') # 1 (Ligar) ou 2 (Desligar)

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Pega os dados da máquina no banco para checar as regras de segurança
    cur.execute("SELECT tipo, switch_id FROM maquinas WHERE porta_ifindex = %s", (porta,))
    maquina = cur.fetchone()
    
    if not maquina:
        return jsonify({"status": "erro", "mensagem": "Porta não encontrada no banco."})
        
    tipo_maquina = maquina[0]
    switch_id = maquina[1]
    
    # Nunca bloquear o professor, servidor ou uplink!
    if tipo_maquina in ['professor', 'servidor', 'uplink'] and str(acao) == '2':
        return jsonify({"status": "erro", "mensagem": f"Operação negada pelo sistema: É proibido cortar a internet de uma máquina do tipo '{tipo_maquina}'."})
        
    # 2. Pega o IP e senha do switch responsável por essa máquina
    cur.execute("SELECT ip_address, snmp_community FROM switches WHERE id = %s", (switch_id,))
    switch = cur.fetchone()
    switch_ip = switch[0]
    community = switch[1]
    
    cur.close()
    conn.close()

    # 3. Manda o Java executar o comando
    try:
        resultado = subprocess.run(
            ["java", "-cp", ".:snmp4j-2.8.18.jar", "GerenteSNMP", switch_ip, community, str(porta), str(acao)],
            cwd="java_snmp", # Informa ao Python que o .jar e o arquivo Java estão dentro dessa pasta
            capture_output=True,
            text=True
        )
        
        saida = resultado.stdout.strip()
        if "SUCESSO" in saida:
            return jsonify({"status": "sucesso", "mensagem": saida})
        else:
            return jsonify({"status": "erro", "mensagem": saida})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)})

@app.route('/alterar_status_sala', methods=['POST'])
def alterar_status_sala():
    data = request.json
    sala_id = data.get('sala_id')
    acao = data.get('acao') # 1 (Ligar) ou 2 (Desligar)

    conn = get_db_connection()
    cur = conn.cursor()
    # Pega APENAS as máquinas dos alunos daquela sala
    cur.execute("""
        SELECT m.porta_ifindex, sw.ip_address, sw.snmp_community 
        FROM maquinas m
        JOIN switches sw ON m.switch_id = sw.id
        WHERE m.sala_id = %s AND m.tipo NOT IN ('professor', 'servidor', 'uplink')
    """, (sala_id,))
    maquinas_alvo = cur.fetchall()
    cur.close()
    conn.close()

    if not maquinas_alvo:
        return jsonify({"status": "aviso", "mensagem": "Nenhuma máquina de aluno encontrada nesta sala."})

    erros = []
    # Roda o Java para cada porta de aluno
    for porta, ip, community in maquinas_alvo:
        try:
            resultado = subprocess.run(
                ["java", "-cp", ".:snmp4j-2.8.18.jar", "GerenteSNMP", ip, community, str(porta), str(acao)],
                cwd="java_snmp", capture_output=True, text=True
            )
            if "SUCESSO" not in resultado.stdout:
                erros.append(f"Porta {porta}: Falhou.")
        except Exception as e:
            erros.append(f"Porta {porta}: {str(e)}")

    if erros:
        return jsonify({"status": "aviso", "mensagem": "Feito, mas com erros:\n" + "\n".join(erros)})
    
    acao_texto = "bloqueadas" if acao == 2 else "liberadas"
    return jsonify({"status": "sucesso", "mensagem": f"Todas as máquinas dos alunos foram {acao_texto} com sucesso!"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

