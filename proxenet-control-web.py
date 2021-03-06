#!/usr/bin/env python2.7
#
#
# proxenet web command control interface
#
#
import os, sys, socket, argparse
import json, cgi, time, atexit
import subprocess, tempfile

try:
    from bottle import request, route, get, post, run, static_file, redirect
except ImportError:
    sys.stderr.write("Missing `bottle` package: pip install bottle\n")
    sys.exit(1)

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_for_filename
    from pygments.formatters import HtmlFormatter
except ImportError:
    sys.stderr.write("Missing `pygments` package: pip install pygments\n")
    sys.exit(1)


__author__    =   "hugsy"
__version__   =   0.2
__licence__   =   "GPL v.2"
__file__      =   "proxenet-control-web.py"
__desc__      =   """proxenet-control-web is a Web interface to control proxenet"""
__usage__     =   """{3} version {0}, {1}
by {2}
syntax: {3} [options] args
""".format(__version__, __licence__, __author__, __file__)

HOME                             = os.getenv("HOME")
PROXENET_ROOT                    = "/opt/proxenet"
PROXENET_BIN                     = PROXENET_ROOT + "/bin"
PROXENET_MISC                    = PROXENET_ROOT + "/misc"
PROXENET_DOCS                    = PROXENET_MISC + "/docs"
PROXENET_HTML                    = PROXENET_DOCS + "/html"
PROXENET_PLUGINS_DIR             = HOME + "/.proxenet/plugins"
PROXENET_AUTOLOAD_DIR            = PROXENET_PLUGINS_DIR + "/autoload"
PROXENET_KEYS_DIR                = HOME + "/.proxenet/keys"
PROXENET_SOCKET_PATH             = "/tmp/proxenet-control-socket"
PROXENET_INI                     = HOME + "/.proxenet/proxenet.ini"
PROXENET_LOGFILE                 = None
PROXENET_DEFAULT_IP              = "0.0.0.0"
PROXENET_DEFAULT_PORT            = 8008


def is_proxenet_running():
    return os.path.exists(PROXENET_SOCKET_PATH)

def success(m):
    return """<div class="alert alert-success alert-dismissible" role="alert">{}</div>""".format(m)

def error(m):
    return """<div class="alert alert-danger alert-dismissible" role="alert">{}</div>""".format(m)

def alert(m):
    return """<div class="alert alert-warning alert-dismissible" role="alert">{}</div>""".format(m)

def redirect_after(n, location):
    return """<script>setTimeout('window.location="{:s}"', {:d})</script>""".format(location, n*1000)

def not_running_html():
    return error("<b>proxenet</b> is not running")

def no_logfile_html():
    return error("Logs are not saved to file.")


def format_result(res):
    d = res.replace('\n', "<br>")
    d = d[:-4]
    return d


def which(program):
    for d in os.getenv("PATH").split(":")+[".", PROXENET_ROOT, PROXENET_ROOT+"/bin"]:
        path = os.path.realpath(d)
        if not os.access(path, os.R_OK | os.X_OK): continue
        exe_file = os.sep.join([path, program])
        if os.path.isfile(exe_file) and os.access(exe_file, os.X_OK):
            return exe_file

    raise IOError("Missing file `%s`" % program)


def recv_until(sock, pattern=">>> "):
    data = ""
    while True:
        data += sock.recv(1024)
        if data.endswith(pattern):
            break
    return data


def sr(msg):
    s = socket.socket( socket.AF_UNIX, socket.SOCK_STREAM )
    try:
        s.connect(PROXENET_SOCKET_PATH)
    except:
        return not_running_html()
    recv_until(s)
    s.send( msg.strip() + '\n' )
    res = recv_until(s)
    s.close()
    return format_result(res)


def build_html(**kwargs):
    header = """<!DOCTYPE html><html lang="en"><head>"""
    header+= """<script src="/js/bootstrap"></script>"""
    header+= """<link rel="stylesheet" href="/css/bootstrap">"""
    header+= """<link rel="stylesheet" href="/css/bootstrap-theme">"""
    header+= """<style>{}</style>""".format( HtmlFormatter().get_style_defs('.highlight') )
    header+= "\n".join( kwargs.get("headers", []) )
    header+= """<title>{}</title></head>""".format( kwargs.get("title", "") )

    body = """<body><div class="container">
    <div><img src="/img/logo"></div>
    <div class="row"><div class=col-md-12>
    <ul class="nav nav-tabs nav-justified">"""

    tabs = []
    if is_proxenet_running():
        tabs.append("info")
        tabs.append("plugin")
        tabs.append("threads")

    tabs += ["config", "keys", "rc"]

    if is_proxenet_running():
        tabs.append("log")
        tabs.append("version")

    for tab in tabs:
        body += """<li {2}><a href="/{0}">{1}</a></li>""".format(tab, tab.capitalize(),
                                                                 "class='active'" if tab==kwargs.get("page") else "")

    if is_proxenet_running():
        body += """<li><a href="#" onclick="var c=confirm('Are you sure to restart?');if(c){window.location='/restart';}">Restart</a></li>"""
        body += """<li><a href="#" onclick="var c=confirm('Are you sure to quit?');if(c){window.location='/quit';}">Quit</a></li>"""
    else:
        body += """<li><a href="/start">Start</a></li>"""

    body += """</ul></div></div>
    <div class="row"><div class="col-md-12"><br></div></div>
    <div class="row">
    </div><div class="col-md-12">{}</div>
    </div></body>""".format( kwargs.get("body", "") )
    footer = """</html>"""
    return header + body + footer


@route('/img/logo')
def logo(): return static_file("/proxenet-logo.png", root=PROXENET_DOCS+"/img")

@route('/favicon.ico')
def favicon(): return static_file("/favicon.ico", root=PROXENET_DOCS+"/img")

@route('/js/jquery')
def js_jquery(): return static_file("/jquery-1.11.2.min.js", root=PROXENET_HTML+"/js")

@route('/js/bootstrap')
def js_bootstrap(): return static_file("/bootstrap.min.js", root=PROXENET_HTML+"/js")

@route('/css/bootstrap')
def css_boostrap(): return static_file("/bootstrap.min.css", root=PROXENET_HTML+"/css")

@route('/css/bootstrap-theme')
def css_boostrap_theme(): return static_file("/bootstrap-theme.min.css", root=PROXENET_HTML + "/css")


@get('/start')
def start():
    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title"><code>proxenet</code> start configuration</h3></div>"""
    html += """<div class="panel-body"><form method="POST"><table boder=0>"""
    html += """<tr><td>Path to <em>proxenet</em> (default "{}"):</td><td><input name="proxenet"/></td><tr>""".format(which("proxenet"))
    html += """<tr><td>Path to <em>proxenet</em> plugins (default "{}"):</td><td><input name="plugins" /></td><tr>""".format(PROXENET_PLUGINS_DIR)
    html += """<tr><td>Listening address (default "{}"):</td><td><input name="address"/></td><tr>""".format(PROXENET_DEFAULT_IP)
    html += """<tr><td>Listening port (default "{}"):</td><td><input name="port"/></td><tr>""".format(PROXENET_DEFAULT_PORT)
    html += """<tr><td>Write logs to (empty = temp file):</td><td><input name="logfile" value="{}"/></td><tr>""".format("/dev/null")
    html += """<tr><td>Forward to proxy (host:port):</td><td><input name="proxy_forward"/></td><tr>"""

    html += """<tr><td>Use SOCKS for proxy forwarding (default HTTP):</td><td><input name="proxy_forward_socks" type="checkbox"/></td><tr>"""
    html += """<tr><td>Do NOT intercept SSL traffic:</td><td><input name="no_ssl_intercept" type="checkbox"/></td><tr>"""
    html += """<tr><td>Use IPv6 (default IPv4 only):</td><td><input name="ipv6" type="checkbox"/></td><tr>"""

    html += """<tr><td><button type="submit" class="btn btn-primary">Start!</button><br/></td><td></td><tr>"""
    html += """</table></form></div>"""
    html += """</div>"""
    return build_html(body=html)


@post('/start')
def do_start():
    global PROXENET_LOGFILE

    msg = ""
    cmd = []

    port = int(request.params.get("port")) if request.params.get("port").isdigit() else PROXENET_DEFAULT_PORT
    addr = request.params.get("address") or PROXENET_DEFAULT_IP
    plugins_dir = request.params.get("plugins") or PROXENET_PLUGINS_DIR
    no_ssl_intercept = True if request.params.get("no_ssl_intercept") else False
    use_ipv6 = "-6" if request.params.get("ipv6") else "-4"
    proxy_use_socks = proxy_forward_host = proxy_forward_port = None
    if request.params.get("proxy_forward"):
        proxy_forward_host, proxy_forward_port = request.params.get("proxy_forward").split(":", 1)
        if request.params.get("proxy_forward_socks"):
            proxy_use_socks = True

    if request.params.get("logfile") is None or len(request.params.get("logfile").strip())==0:
        logfile_fd, logfile = tempfile.mkstemp(suffix=".log", prefix="proxenet-", dir="/tmp", text=True)
        os.close(logfile_fd)
    else:
        logfile = request.params.get("logfile")

    PROXENET_LOGFILE = logfile

    cmd.append(PROXENET_BIN + "/proxenet")
    cmd.append("--daemon")
    cmd.append("--bind=%s" % addr)
    cmd.append("--port=%d" % port)
    cmd.append("--plugins=%s" % plugins_dir)
    cmd.append("--logfile=%s" % logfile)
    cmd.append("--certfile=%s" % PROXENET_KEYS_DIR+"/proxenet.crt")
    cmd.append("--keyfile=%s" % PROXENET_KEYS_DIR+"/proxenet.key")
    cmd.append(use_ipv6)
    if no_ssl_intercept:
        cmd.append("--no-ssl-intercept")
    if proxy_forward_host and proxy_forward_port:
        cmd.append("--proxy-host=%s" % proxy_forward_host)
        cmd.append("--proxy-port=%s" % proxy_forward_port)
        if proxy_use_socks: cmd.append("--use-socks")

    popup = "Launching <b>proxenet</b> with command:<br/><br/>"
    popup+= """<div style="font: 100% Courier,sans-serif;">""" + " ".join(cmd) + """</div>"""
    msg+= alert(popup)
    subprocess.call(cmd)
    msg+= redirect_after(2, "/info")
    return build_html(body=msg)


@get('/quit')
def quit():
    if not is_proxenet_running(): return build_html(body=not_running_html())
    sr("quit")
    msg = ""
    msg+= alert("Shutting down <b>proxenet</b> , thanks for using it")
    msg+= redirect_after(2, "/info")
    return build_html(body=msg)


@get('/restart')
def restart():
    if not is_proxenet_running(): return build_html(body=not_running_html())
    sr("restart")
    msg = ""
    msg+= alert("Restarting <b>proxenet</b>")
    msg+= redirect_after(2, "/info")
    return build_html(body=msg)


@get('/info')
def info():
    if not is_proxenet_running():
        return build_html(body=not_running_html())

    res = sr("info")
    info = json.loads(res)['info']

    html = ""
    for section in info.keys():
        html += """<div class="panel panel-default">"""
        html += """<div class="panel-heading"><h3 class="panel-title">{}</h3></div>""".format(section)

        html += """<div class="panel-body"><ul>"""
        for k,v in info[section].iteritems():
            if type(v).__name__ == "dict":
                html += "<li>{}: <ol>".format(k)
                for a,b in v.iteritems(): html += "<li>{}: {}</li>".format(a,b)
                html += "</ol></li>"
            else:
                html += "<li>{}: {}</li>".format(k, v)
        html += "</ul></div></div>"""

    return build_html(body=html, title="Info page", page="info")


@get('/version')
def version():
    if not is_proxenet_running():
        return build_html(body=not_running_html())

    res = sr("version")
    version = json.loads(res)
    html = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Version information</h3></div>"""
    html += """<div class="panel-body"><ul>"""
    for k,v in version.iteritems():
        html += "<li>"
        if k=="vms":
            html += "VMs"
            html += "<ol>"
            html += ''.join(["<li>{}</li>".format(x.strip()) for x in v if len(x.strip())>0])
            html += "</ol>"
        else:
            html += "{}: {}".format(k.capitalize(), v)
        html += "</li>"

    html += """</ul></div></div>"""

    return build_html(body=html, title="Version page", page="version")



@route('/')
@route('/index')
def index():
    return info()


@get('/plugin')
def plugin():
    if not is_proxenet_running(): return build_html(body=not_running_html())
    html = ""

    # enabled plugins
    res = sr("plugin list")
    js = json.loads( res )
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Plugins loaded</h3></div>"""
    html += """<table class="table table-hover table-condensed">"""
    html += "<tr><th>Id</th><th>Name</th><th>Priority</th><th>Type</th><th>Status</th><th>Action</th></tr>"
    for name in js.keys():
        p = js[name]
        html += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>".format(p['id'], name, p['priority'], p['type'], p['state'])
        if p['state']=="INACTIVE":
            html += """<td><button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="false" onclick="window.location='/plugin/{}/enable'">Enable</button></td>""".format(p["id"])
        else:
            html += """<td><button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="false" onclick="window.location='/plugin/{}/disable'">Disable</button></td>""".format(p["id"])
        html += "</tr>"
    html += "</table></div>"""

    time.sleep(0.10)

    # available plugins
    res = sr("plugin list-all")
    js = json.loads( res )
    title = js.keys()[0]
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">{}</h3></div>""".format(title)
    html += """<table class="table table-hover table-condensed">"""
    html += "<tr><th>Name</th><th>Type</th><th>Enabled</th><th>Autoload?</th></tr>"
    for k,v in js[title].iteritems():
        _type, _is_loaded = v
        html += "<tr><td><a href=\"/plugin/view/{0}\">{0}</a></td><td>{1}</td>".format(k, _type)
        html += "<td>"
        if _is_loaded:
            html += """<input type="checkbox" checked="true" disabled="true"/>"""
        else:
            html += """<input type="checkbox" onclick="window.location='/plugin/load/{}'"/>""".format(k)
        html += "</td>"
        html += "<td>"
        fpath = os.path.abspath(PROXENET_ROOT + "/proxenet-plugins/autoload/" + k)

        if os.path.islink(fpath):
            html += """<button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="true" disabled='true'">Added</button>"""
            html += """<button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="false" onclick="window.location='/plugin/unautoload/{}'">Remove</button>""".format(k)
        else:
            html += """<button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="false" onclick="window.location='/plugin/autoload/{}'">Add</button>""".format(k)
            html += """<button type="button" class="btn btn-default btn-xs" data-toggle="button" aria-pressed="true" disabled='true'>Removed</button>"""

        html += "</td>"

        html += "</tr>"
    html += "</table></div>"""

    return build_html(body=html, title="Plugins detail", page="plugin")


@get('/plugin/load/<fname>')
def plugin_load(fname):
    if not is_proxenet_running(): return build_html(body=not_running_html())
    fname = cgi.escape(fname)
    res = sr("plugin load {}".format(fname))
    html = ""
    if "error" in res:
        html += error("Failed to load <b>{}</b>".format(fname))
    else:
        html = success("<b>{}</b> loaded successfully".format(fname))
    html+= redirect_after(2, "/plugin")
    return build_html(body=html, page="plugin", title="Adding plugin {}".format(fname))


@get('/plugin/unautoload/<fname>')
def plugin_remove_from_autoload(fname):
    if not is_proxenet_running(): return build_html(body=not_running_html())
    fname = cgi.escape(fname)
    flink = os.path.realpath( PROXENET_AUTOLOAD_DIR + '/' + fname)
    html = ""
    if not os.path.islink(flink):
        html += error("Failed to remove '<b>{}</b>' from autoload directory".format(fname))
    else:
        os.unlink(flink)
        html += success("<b>{}</b> successfully removed from autoload directory".format(fname))
    html+= redirect_after(2, "/plugin")
    return build_html(body=html, page="plugin", title="Removing from autoload")


@get('/plugin/autoload/<fname>')
def plugin_add_to_autoload(fname):
    if not is_proxenet_running(): return build_html(body=not_running_html())
    fname = cgi.escape(fname)
    fpath = os.path.abspath(PROXENET_PLUGINS_DIR + "/" + fname)
    html = ""
    if not os.path.isfile(fpath):
         html+= error("Failed to load <b>{}</b>".format(fname))
    else:
        flink = os.path.realpath(PROXENET_AUTOLOAD_DIR + "/" + fname)
        os.symlink(fpath, flink)
        html+= success("<b>{}</b> loaded successfully".format(fname))
    html+= redirect_after(2, "/plugin")
    return build_html(body=html, page="plugin")


@get('/plugin/<id:int>/<action>')
def plugin_toggle(id,action):
    if not is_proxenet_running(): return build_html(body=not_running_html())
    res = sr("plugin set {} toggle".format(id))
    html = ""
    if "error" in res:
        html += error("""Failed to change state for plugin {}""".format(id))
    else:
        html += success("""Plugin {} state changed""".format(id))
    html+= redirect_after(2, "/plugin")
    return build_html(body=html, page="plugin")


@get('/plugin/view/<fname>')
def plugin_view(fname):
    if not is_proxenet_running():
        return build_html(body=not_running_html())
    fname = cgi.escape(fname)
    fpath = os.path.realpath(PROXENET_ROOT + "/proxenet-plugins/" + fname)
    if not os.path.isfile(fpath):
        return build_html(body=error("""<b>{}</b> is not a valid plugin""".format(fname)))

    if fpath.endswith(".class"):
        fpath = fpath.replace(".class", ".java")
        fname = fname.replace(".class", ".java")
        if not os.path.isfile(fpath):
            return build_html(body=error("""<b>{}</b> is not a valid plugin""".format(fname)))

    with open(fpath, 'r') as f:
        code = f.read()

    lexer = get_lexer_for_filename(fname)
    html  = """"""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">{}</h3></div>""".format(fpath)
    html += """<div class="panel-body">"""
    html += """{}""".format( highlight(code, lexer, HtmlFormatter()) )
    html += """</div>"""
    html += """</div>"""
    return build_html(body=html, page="plugin", title="Viewing plugin '{}'".format(fname))


@get('/threads')
def threads():
    if not is_proxenet_running(): return build_html(body=not_running_html())
    res = sr("threads")
    js = json.loads( res )
    title = js.keys()[0]
    html = ""

    if request.params.get("msg"):
        msg = request.params.get("msg").strip()
        msg = msg.replace("%20", " ")
        html+= success(cgi.escape(msg))

    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">{}</h3></div>""".format(title)
    html += """<div class="panel-body"><ul>"""
    for k,v in js[title].iteritems():
        if v.__class__.__name__ == "dict":
            html += "<li>{}:<ol>".format(k)
            for a,b in v.iteritems():
                html += "<li>"
                html += "{} &#8594; {}".format(a,b)
                html += "<a href='/threads/kill?tid={}'>&#x2718;</a>".format(b)
                html += "</li>"

            html += "</li>"
        else:
            html += "<li>{}: {}</li>".format(k, v)
    html += "</ul></div></div>"""

    html += """<div class="col-lg-6"><div class="btn-group" role="group" aria-label="">
    <button type="button" class="btn btn-default" onclick="window.location='/threads/inc'">Increment</button>
    <button type="button" class="btn btn-default" onclick="window.location='/threads/dec'">Decrement</button>
    </div></div>"""
    return build_html(body=html, title="Get information on Threads", page="threads")


@get('/threads/<word>')
def threads_set(word):
    tid = ""
    if not is_proxenet_running():
        return build_html(body=not_running_html())

    if word not in ("inc", "dec", "kill"):
        return build_html(body=error("Invalid action"), page="threads")

    if word=="kill":
        if not request.params.get("tid"):
            return build_html(body=error("Invalid ThreadId"), page="threads")

        tid = request.params.get("tid").strip()
        if not tid.isdigit():
            return build_html(body=error("Invalid ThreadId"), page="threads")

    if word == "kill":
        res = sr("threads kill {}".format(tid))
    else:
        res = sr("threads {}".format(word))

    redirect("/threads?msg={}".format(res))
    return


@route('/keys')
def keys():
    extensions = [ ("PEM formatted certificate", "crt"), ("PEM formatted private key", "key"),
                   ("PKCS12 formatted certificate+key", "p12"), ("PKCS7 formatted certificate", "p7b"), ]
    html = """<div class="panel panel-default">"""
    html+= """<div class="panel-heading"><h3 class="panel-title">SSL keys</h3></div>"""
    html+= """<div class="panel-body"><ul>"""
    for ext,fmt in extensions: html += """<li><a href="/keys/proxenet.{}">{}</a></li>""".format(fmt, ext)
    html+= "</ul></div>"
    return build_html(body=html, title="Get proxenet SSL keys", page="keys")


@route('/keys/proxenet.<fmt>')
def key(fmt):
    if fmt in ("crt", "key", "p12", "p7b"):
        return static_file("/proxenet.%s" % fmt, root=PROXENET_ROOT + "/keys")


@route('/config')
def config():
    if not is_proxenet_running(): return build_html(body=not_running_html())
    res = sr("config list")
    js = json.loads( res )
    title = js.keys()[0]
    values = js[title]

    # view config
    html  = """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">{}</h3></div>""".format( title )
    html += """<div class="panel-body">"""
    html += """<table class="table table-hover table-condensed">"""
    html += """<tr><th>Setting</th><th>Value</th><th>Type</th></tr>"""
    for k,v in values.iteritems():
        _val, _type = v["value"], v["type"]
        html += "<tr><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(k,_val,_type)
    html += "</table></div></div>"""

    # edit config
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Change Value</h3></div>"""
    html += """<div class="panel-body"><form class="form-inline" action="/config/set" method="get">"""
    html += """<div class="form-group"><select class="form-control" name="setting">"""
    for k,v in values.iteritems():
        html += """<option>{}</option>""".format( k )
    html += """</select></div><div class="form-group"><label class="sr-only">Value</label><input class="form-control" name="value" placeholder="Value"></div><button type="submit" class="btn btn-default">Change Value</button>"""
    html += """</form></div></div>"""
    return build_html(body=html, title="proxenet Configuration", page="config")


@route('/config/set')
def config_set():
    if not is_proxenet_running(): return build_html(body=not_running_html())
    param = request.params.get("setting")
    value = request.params.get("value")
    res = sr("config set {} {}".format(param, value))
    js = json.loads( res )
    retcode = js.keys()[0]
    if retcode == "error":
        return """<div class="alert alert-danger" role="alert">{}</div>""".format(res[retcode])
    redirect("/config")
    return


@get('/rc')
def view_plugin_params():
    if not os.access(PROXENET_INI, os.R_OK):
        open(PROXENET_INI, 'a+')
    with open(PROXENET_INI, 'r+') as f:
        code = f.read()
    html  = ""

    if request.params.get("new"):
        html += success("New configuration written")

    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Edit plugin config</h3></div>"""
    html += """<div class="panel-body"><form method="POST">"""
    html += """<textarea name="config" cols="120" rows="20" style="font: 100% Courier,sans-serif;">{}</textarea><br/>""".format(code)
    html += """<button type="submit" class="btn btn-primary">Submit</button><br/>"""
    html += """</form></div>"""
    html += """</div>"""
    return build_html(body=html, page="rc", title="Viewing plugin configuration file")


@post('/rc')
def write_plugin_params():
    with open(PROXENET_INI, 'w') as f:
        f.write( request.params.get("config") )
    success("New configuration written")
    redirect("/rc?new=1")
    return


@get('/log')
def view_logfile():
    global PROXENET_LOGFILE

    if not is_proxenet_running(): return build_html(body=not_running_html())
    if PROXENET_LOGFILE in (None, "", "/dev/null"): return build_html(body=no_logfile_html())

    with open(PROXENET_LOGFILE, 'r') as f:
        logs = f.read()

    headers = ["""<meta http-equiv="refresh" content="5"/>""", ]

    html  = ""
    html += """<div class="panel panel-default">"""
    html += """<div class="panel-heading"><h3 class="panel-title">Logs from '{}'</h3></div>""".format(PROXENET_LOGFILE)
    html += """<div class="panel-body">"""
    html += """<textarea name="logs" cols="130"  rows="30" style="font: 100% Courier,sans-serif;" readonly>{}</textarea><br/>""".format(logs)
    html += """</div>"""
    html += """</div>"""
    return build_html(body=html, page="log", title="Log file", headers=headers)


def kill_daemon():
    os.remove( os.getpid() )
    return


def daemon():
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.setsid()
    os.umask(0)

    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    sys.stdout.flush()
    sys.stderr.flush()
    si = file("/dev/null", 'r')
    so = file("/dev/null", 'a+')
    se = file("/dev/null", 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    atexit.register(kill_daemon)
    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(usage = __usage__, description = __desc__)

    parser.add_argument("-v", "--verbose", default=False, action="store_true",
                        dest="verbose", help="Increments verbosity")

    parser.add_argument("-d", "--debug", default=False, action="store_true",
                        dest="debug", help="Enable `bottle` debug mode")

    parser.add_argument("-D", "--demonize", default=False, action="store_true",
                        dest="daemon", help="Daemonize the web server")

    parser.add_argument("-H", "--host", default="localhost", type=str, dest="host",
                        help="IP address to bind")

    parser.add_argument("-P", "--port", default=8009, type=int, dest="port",
                        help="port to bind")

    args = parser.parse_args()

    if args.daemon:
        print("Starting web server as daemon on http://%s:%d" % (args.host,args.port))
        daemon()

    run(host=args.host, port=args.port, debug=args.debug)

    sys.exit(0)
