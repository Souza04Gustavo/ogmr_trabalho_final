from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import psycopg2
import subprocess
from datetime import datetime, timedelta
import os
import re

app = Flask(__name__)

# Configurações do seu banco Postgres
DB_HOST = "localhost"
DB_NAME = "projeto_ogmr"
DB_USER = "postgres"
DB_PASS = "postgres"

app.secret_key = 'chave_super_secreta_projeto_redes'

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

def checar_status_porta(ip, porta):
    try:
        # Vamos usar o nome exato da MIB que testamos antes e funcionou perfeitamente
        oid = f"IF-MIB::ifAdminStatus.{porta}"
        
        resultado = subprocess.run(
            ["snmpget", "-v2c", "-c", "public", "-r", "1", "-Oqv", ip, oid],
            capture_output=True, text=True, timeout=5
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

def agendar_desbloqueio(ip, community, porta, minutos):
    agora = datetime.now()
    futuro = agora + timedelta(minutes=int(minutos))
    
    # Formato do crontab Linux: MINUTO HORA DIA MES DIA_DA_SEMANA COMANDO
    cron_time = f"{futuro.minute} {futuro.hour} {futuro.day} {futuro.month} *"
    
    cwd = os.path.abspath("java_snmp")
    comando = f"cd {cwd} && java -cp .:snmp4j-2.8.18.jar GerenteSNMP {ip} {community} {porta} 1"
    
    cron_job = f"{cron_time} {comando}\n"
    
    # Executa comando bash que pega o crontab atual e insere a nova linha
    os.system(f"(crontab -l 2>/dev/null; echo \"{cron_job}\") | crontab -")

def obter_mac_cliente(ip):
    if ip == '127.0.0.1' or ip == 'localhost':
        try:
            out_mac = subprocess.check_output("ip link show", shell=True).decode()
            # Pega todos os MACs físicos reais (ignorando o loopback vazio)
            macs = re.findall(r"link/ether (([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", out_mac)
            if macs:
                return macs[0][0].upper() # Retorna o MAC físico do Professor
        except Exception:
            pass

    try:
        with open('/proc/net/arp') as f:
            for linha in f:
                if linha.startswith(ip + ' '):
                    mac = linha.split()[3]
                    if mac != '00:00:00:00:00:00':
                        return mac.upper()
    except Exception:
        pass
        
    try:
        out = subprocess.check_output(f"ip -o addr show | grep ' {ip}/'", shell=True).decode()
        iface = out.split()[1]
        out_mac = subprocess.check_output(f"ip link show {iface}", shell=True).decode()
        mac = re.search(r"link/ether (([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", out_mac)
        if mac:
            return mac.group(1).upper()
    except Exception:
        pass

    return "MAC_DESCONHECIDO"

@app.route('/')
def index():
    ip_visitante = request.remote_addr
    mac_visitante = obter_mac_cliente(ip_visitante)

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Pega a SALA exata onde esse professor dá aula
    cur.execute("SELECT sala_id FROM maquinas WHERE UPPER(mac_address) = UPPER(%s) AND tipo = 'professor'", (mac_visitante,))
    professor_valido = cur.fetchone()
    
    if not professor_valido:
        cur.close()
        conn.close()
        return render_template('acesso_negado.html', ip_visitante=ip_visitante, mac_visitante=mac_visitante), 403

    if not session.get('logado'):
        cur.close()
        conn.close()
        return redirect(url_for('login'))

    prof_sala_id = professor_valido[0]

    # 2. Filtra as máquinas SOMENTE pela sala do professor (WHERE m.sala_id = %s)
    cur.execute("""
        SELECT m.mac_address, m.nome_host, m.ip_address, m.mac_address, m.porta_ifindex, m.tipo,
               s.nome as sala_nome, sw.ip_address as switch_ip, s.id as sala_id
        FROM maquinas m
        JOIN salas s ON m.sala_id = s.id
        JOIN switches sw ON m.switch_id = sw.id
        WHERE m.sala_id = %s
        ORDER BY m.tipo DESC, m.nome_host;
    """, (prof_sala_id,))
    linhas_db = cur.fetchall()
    cur.close()
    conn.close()

    # Descobre o nome da sala (pega da primeira máquina da lista)
    sala_nome = linhas_db[0][6] if linhas_db else "Sala Desconhecida"

    maquinas = []
    for m in linhas_db:
        ip_switch = m[7]
        porta = m[4]
        status_atual = checar_status_porta(ip_switch, porta)
        m_lista = list(m)
        m_lista.append(status_atual) 
        maquinas.append(m_lista)

    # 3. Envia os dados da sala para o HTML montar o rodapé
    return render_template('index.html', maquinas=maquinas, sala_nome=sala_nome, sala_id=prof_sala_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip_visitante = request.remote_addr
    mac_visitante = obter_mac_cliente(ip_visitante)
    erro = None
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM maquinas WHERE UPPER(mac_address) = UPPER(%s) AND tipo = 'professor'", (mac_visitante,))
    valido = cur.fetchone()
    cur.close()
    conn.close()
    
    if not valido:
        return render_template('acesso_negado.html', ip_visitante=ip_visitante, mac_visitante=mac_visitante), 403

    if request.method == 'POST':
        senha = request.form.get('senha')
        if senha == 'admin123':  # Senha correta
            session['logado'] = True
            return redirect(url_for('index'))
        else:
            erro = "Senha incorreta. Tente novamente."

    return render_template('login.html', erro=erro)

@app.route('/logout')
def logout():
    session.pop('logado', None)
    return redirect(url_for('login'))

@app.route('/alterar_status', methods=['POST'])
def alterar_status():
    data = request.json
    porta = data.get('porta')
    acao = data.get('acao') # 1 (Ligar) ou 2 (Desligar)
    minutos = data.get('minutos')

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
            cwd="java_snmp", capture_output=True, text=True
        )
        
        saida = resultado.stdout.strip()
        if "SUCESSO" in saida:
            # FASE 7: Se tem minutos agendados e é ação de Bloqueio(2), chama o Crontab
            if str(acao) == '2' and minutos and str(minutos).isdigit():
                agendar_desbloqueio(switch_ip, community, porta, int(minutos))
                return jsonify({"status": "sucesso", "mensagem": f"{saida} (Desbloqueio agendado para daqui a {minutos} min)"})
                
            return jsonify({"status": "sucesso", "mensagem": saida})
        else:
            return jsonify({"status": "erro", "mensagem": saida})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)})

@app.route('/status_portas')
def status_portas():
    if not session.get('logado'):
        return jsonify({"erro": "Nao logado"}), 403
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT m.porta_ifindex, sw.ip_address FROM maquinas m JOIN switches sw ON m.switch_id = sw.id")
    maquinas = cur.fetchall()
    cur.close()
    conn.close()

    status_dict = {}
    for porta, ip in maquinas:
        status_dict[porta] = checar_status_porta(ip, porta)
        
    return jsonify(status_dict)

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

