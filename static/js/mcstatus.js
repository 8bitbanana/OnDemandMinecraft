const startMainServer = async () => {
    disableButtons()
    var response = await fetch("/startserver", {
        method: "POST",
        headers: {
            'Content-Type':'application/json'
        }
    })
}

const startMcServer = async () => {
    disableButtons()
    var response = await fetch("/startmcserver", {
        method: "POST",
        headers: {
            'Content-Type':'application/json'
        }
    })
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

var disableLock = false;
const disableButtons = async () => {
    disableLock = true;
    document.getElementById("mainStart").disabled = true;
    document.getElementById("mcStart").disabled = true;
    await sleep(5000);
    disableLock = false;
} 

const mainStatusDict = {
    "pending": "Starting up",
    "running": "Online",
    "shutting-down": "Offline",
    "terminated": "Deleted",
    "stopping": "Shutting down",
    "stopped": "Offline"
}

const mcStatusDict = {
    null:"Unreachable",
    "stopped":"Offline",
    "starting-blank":"(1/3) Warming up",
    "starting-launching":"(2/3) Launching",
    "starting-preparing":"(3/3) Preparing world",
    "running":"Online",
    "stopped-ssh":"Offline (SSH Connected)",
    "stopping":"Shutting down",
    "unknown":"Unknown"
}


const updateServerStatus = async () => {
    var response = await fetch("/serverstatus", {
        method: 'GET',
        headers: {
            'Content-Type':'application/json'
        }
    });
    var data = await response.json();

    var mainStatus = data['main']
    var mcStatus = data['mc']
    
    if (!disableLock) {
        if (mainStatus == "stopped" || mainStatus == "stopped-ssh") {
            document.getElementById("mainStart").disabled = false;
        } else {
            document.getElementById("mainStart").disabled = true;
        }

        if (mcStatus == "stopped" || mcStatus == "stopped-ssh") {
            document.getElementById("mcStart").disabled = false;
        } else {
            document.getElementById("mcStart").disabled = true;
        }
    }

    mainStatusStr = mainStatusDict[mainStatus]
    if (data['ssh']) {
        mainStatusStr += " (Remote connected)"
    }
    document.getElementById("mainStatus").innerHTML = mainStatusStr;
    document.getElementById("mcStatus").innerHTML = mcStatusDict[mcStatus];

    var serverIp = data['ip'];
    if (serverIp == null) {
        document.getElementById("serverIp").innerHTML = "-";
    } else {
        document.getElementById("serverIp").innerHTML = data['ip'];
    }

    if (mcStatus != null) {
        var players = data['players']
        var playerStr = ""
        for (var player in players) {
            var online = players[player]
            if (online) {
                css_class = "player-online"
            } else {
                css_class = "player-offline"
            }
            playerStr += "<a class=\"" + css_class + "\">" + player + "</a> "
        }
        document.getElementById("currentPlayers").innerHTML = playerStr;
        document.getElementById("playersDiv").style = "";
    } else {
        document.getElementById("playersDiv").style = "display: none;"
    }
}

function copyip() {
    var copyText = document.getElementById("serverIp");
    var textArea = document.createElement("textarea");
    textArea.value = copyText.innerHTML;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand("Copy");
    textArea.remove();
    tooltip = document.getElementsByClassName("tooltiptext")[0];
    tooltip.innerHTML = "Copied!";
    setTimeout(restoreTooltip, 1000);
}

function restoreTooltip() {
    tooltip = document.getElementsByClassName("tooltiptext")[0];
    tooltip.innerHTML = "Click to copy";
}

updateServerStatus();
setInterval(updateServerStatus, 2000);