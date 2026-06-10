#  Sistema de Gerenciamento de Acesso à Internet via SNMP

Repositório destinado ao projeto final da disciplina de **Gerência e Mobilidade em Redes**, ministrada pelo Prof. Adriano Fiorese na Universidade do Estado de Santa Catarina (UDESC).

## Sobre o Projeto
O objetivo deste projeto é implementar um sistema de controle de acesso à Internet utilizando técnicas de gerência de redes (Protocolo SNMP). O sistema permite que um professor gerencie, através de uma interface Web, o bloqueio ou a liberação da conexão de internet de máquinas específicas de uma sala de aula de forma imediata ou coletiva, desabilitando logicamente as portas do switch (alterando o `ifAdminStatus`).

## Arquitetura do Sistema
O sistema foi desenvolvido utilizando uma arquitetura baseada em microsserviços e integração de múltiplas linguagens para atender aos requisitos da disciplina:

1. **Frontend (Interface Web):** Desenvolvido em HTML5, CSS (Bootstrap) e JavaScript (AJAX). Responsável por exibir o status em tempo real e receber os comandos do usuário.
2. **Backend (Controlador):** Desenvolvido em **Python (Flask)**. Atua como o cérebro da aplicação, validando o IP de acesso (segurança), gerenciando a sessão de login e cruzando dados lógicos.
3. **Banco de Dados:** **PostgreSQL**. Mantém o mapeamento da infraestrutura física (Switch ↔ Sala ↔ Máquina ↔ Porta `ifIndex`).
4. **Motor SNMP (Agente de Rede):** Desenvolvido em **Java** usando a API **SNMP4J**. É compilado e executado em background pelo Python para disparar mensagens SNMP `SET`.
5. **Simulador de Equipamento (Switch):** Utilizou-se o serviço `snmpd` do Linux (Ubuntu) com interfaces de rede virtuais (`dummy`) para simular as portas físicas de um switch gerenciável localmente.

---

## Estrutura do Repositório

```text
ogmr_trabalho_final/
├── java_snmp/               # Diretório do Motor SNMP
│   ├── GerenteSNMP.java     # Código fonte Java responsável pelo envio do PDU
│   ├── GerenteSNMP.class    # Arquivo compilado 
│   └── snmp4j-2.8.18.jar    # Biblioteca oficial da API SNMP4J
├── templates/               # Diretório de views do Flask
│   └── index.html           # Interface do painel do professor
├── app.py                   # Aplicação principal Backend (Flask)
├── enunciado_tf.pdf         # Especificação original do trabalho
└── README.md                # Documentação do projeto
```

---

## Configuração do Ambiente de Testes (Ubuntu Linux)

Para executar este projeto localmente, é necessário simular o switch, configurar o banco de dados e instalar as dependências de software. Siga os passos abaixo:

### 1. Dependências Básicas
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv default-jdk postgresql -y
```

### 2. Configurando o "Switch Simulado" (SNMP Daemon e Portas dummy)
Vamos criar interfaces de rede virtuais para simular as portas do switch:
```bash
sudo modprobe dummy
sudo ip link add porta_prof type dummy
sudo ip link add porta_sala_1 type dummy
sudo ip link add porta_sala_2 type dummy
```

Instale o agente e as ferramentas SNMP:
```bash
sudo apt install snmpd snmp snmp-mibs-downloader -y
```

Libere a leitura das MIBs editando o arquivo cliente `sudo nano /etc/snmp/snmp.conf` e comentando a linha `mibs :`:
```text
#mibs :
```

Configure o agente SNMP como "Switch" editando `sudo nano /etc/snmp/snmpd.conf` e garantindo as linhas:
```text
agentAddress udp:127.0.0.1:161
rocommunity public default
rwcommunity private default
```

Conceda privilégios de root ao SNMP para que ele possa desligar as interfaces de rede:
```bash
# Edite o serviço: sudo nano /lib/systemd/system/snmpd.service
# Altere a linha ExecStart removendo as tags de usuário restrito (-u Debian-snmp -g Debian-snmp).
# Deve ficar parecido com: ExecStart=/usr/sbin/snmpd -LOw -I -smux,mteTrigger,mteTriggerConf -f
sudo systemctl daemon-reload
sudo systemctl restart snmpd
```

### 3. Configurando o Banco de Dados (PostgreSQL)
Acesse o prompt do banco:
```bash
sudo -u postgres psql
```
Altere a senha do usuário padrão para a aplicação se conectar:
```sql
ALTER USER postgres PASSWORD 'postgres';
CREATE DATABASE projeto_ogmr;
\c projeto_ogmr
```
Crie as tabelas e insira os dados do ambiente de teste simulado:
```sql
CREATE TABLE switches (id SERIAL PRIMARY KEY, nome VARCHAR(50), ip_address VARCHAR(50), snmp_community VARCHAR(50) DEFAULT 'private');
CREATE TABLE salas (id SERIAL PRIMARY KEY, nome VARCHAR(50));
CREATE TABLE maquinas (id SERIAL PRIMARY KEY, nome_host VARCHAR(50), ip_address VARCHAR(50) UNIQUE, mac_address VARCHAR(50) UNIQUE, sala_id INT, switch_id INT, porta_ifindex INT, tipo VARCHAR(20) DEFAULT 'aluno');

-- Populando o banco com o cenário do simulador local
INSERT INTO switches (nome, ip_address, snmp_community) VALUES ('Switch_Core', '127.0.0.1', 'private');
INSERT INTO salas (nome) VALUES ('Sala F203');
INSERT INTO maquinas (nome_host, ip_address, mac_address, sala_id, switch_id, porta_ifindex, tipo) VALUES ('PC-Professor', '127.0.0.1', 'AA:BB:CC:DD:EE:11', 1, 1, 11, 'professor');
INSERT INTO maquinas (nome_host, ip_address, mac_address, sala_id, switch_id, porta_ifindex, tipo) VALUES ('PC-Aluno-01', '192.168.1.101', 'AA:BB:CC:DD:EE:22', 1, 1, 12, 'aluno');
INSERT INTO maquinas (nome_host, ip_address, mac_address, sala_id, switch_id, porta_ifindex, tipo) VALUES ('PC-Aluno-02', '192.168.1.102', 'AA:BB:CC:DD:EE:33', 1, 1, 13, 'aluno');
\q
```

### 4. Executando a Aplicação
Crie e ative um ambiente virtual para o Python:
```bash
python3 -m venv venv
source venv/bin/activate
pip install Flask psycopg2-binary
```

Compile o motor Java (certifique-se de estar na raiz do projeto):
```bash
cd java_snmp
javac -cp snmp4j-2.8.18.jar GerenteSNMP.java
cd ..
```

Inicie o servidor Web Backend:
```bash
python3 app.py
```

### 5. Uso e Acesso
Acesse a aplicação no navegador através de: `http://localhost:5000`.
* O sistema possui uma validação de IP embutida. Apenas a máquina registrada como `professor` (no caso, seu localhost `127.0.0.1`) tem acesso à tela de login.
* **Senha padrão:** `admin123`

---
## ATENÇÃO: O TRABALHO AINDA NÃO ESTA COMPLETO!
O sistema de login ainda esta ausente na versão atual e o sistema de agendamento por horarios tambem esta de fora!
