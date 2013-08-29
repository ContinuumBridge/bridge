#!/usr/bin/env bash

function sethost {
    echo -n "host ($aggregatorhost):"
    read aggregatorhost
}

function setaggregatorport {
    echo -n "port ($aggregatorport):"
    read aggregatorport
}

function setdeviceport {
    echo -n "port ($deviceport):"
    read deviceport
}

function setapp {
    echo -n "app ($theapp):"
    read theapp
}

function setdevice {
    echo -n "device ($thedevice):"
    read thedevice
}

function removesockets {
    if [ "$theapp" != "" ]; then
        rm -fr /lxc/$theapp
    fi
}

function startaggregator {
    pushd $basedir/aggregator
    node $theserver &
    popd
    pids+=($!)
    # Print last element
    echo "Aggregator ${pids[@]: -1}"
}

function startaggregatorchannel {
    $builddir/concentrator/setupChannel "$theapp:outaggregator" "$aggregatorhost:$aggregatorport" isdownstream &
    pids+=($!)
    # Print last element
    echo "Aggregator channel ${pids[@]: -1}"
}

function startdevicechannel {
    $builddir/concentrator/setupChannel "$theapp:inbasedev" "$devicehost:$deviceport" &
    pids+=($!)
    # Print last element
    echo "Device channel ${pids[@]: -1}"
}

function startdevice {
    $builddir/devices/$thedevice "$devicehost:$deviceport" &
    pids+=($!)
    # Print last element
    echo "startdevice - Device ${pids[@]: -1}"
}

function startdriver {
    # Find the driver, may either be in the build directory if C,
    # otherwise in repository if python
    if [ -e $builddir/drivers/$thedriver ]; then
        drvfile=$builddir/drivers/$thedriver
    else
        if [ -e $basedir/drivers/$thedriver ]; then
            drvfile=$basedir/drivers/$thedriver
        else
            echo "Unable to find driver $thedriver"
            exit 1
        fi
    fi

    PYTHONPATH=lib $drvfile $driverparams &
    pids+=($!)
    # Print last element
    echo "Driver ${pids[@]: -1}"
}

function startapp {
    # Check that template is installed
    cp ../lxc-scripts/lxc-cb /usr/share/lxc/templates/

    # Find the app, may either be in the build directory if C,
    # otherwise in repository if python
    if [ -e $builddir/apps/$theapp ]; then
        appfile=$builddir/apps/$theapp
    else
        if [ -e $basedir/apps/$theapp ]; then
            appfile=$basedir/apps/$theapp
        else
            echo "Unable to find app $theapp"
            exit 1
        fi
    fi
    lxc-destroy -n "lxc-$theapp" || true
    lxc-create -n "lxc-$theapp" -t cb -f $basedir/lxc-scripts/app.conf -- -A $appfile -P $builddir/lib
    screen -dmS "lxc-$theapp" lxc-start -n "lxc-$theapp"
    # Check still running
    sleep 5
    if ! screen -ls "lxc-$theapp" | grep "lxc-$theapp" > /dev/null; then
        echo "lxc lxc-$theapp not running, try running without screen"
        lxc-start -n "lxc-$theapp"
        exit 1
    fi
}

function single {
    aggregatorhost=localhost
    devicehost=localhost
    removesockets
    startaggregator
    startaggregatorchannel
    startdevice
    startdevicechannel
    startapp
}

function laptopsensortag {
    aggregatorhost=localhost
    theserver=sensortagserver.js
    theapp=sensortagapp
    thedriver=sensortagdriver.py
    driverparams="hci1 90:59:AF:04:2B:92 $theapp:insensortag"
    removesockets
    startaggregator
    startaggregatorchannel
    startdriver
    startapp
}

function sensortagaggregator {
    theserver=sensortagserver.js
    startaggregator
}

function rpisensortag {
    aggregatorhost=localhost
    theapp=sensortagapp
    thedriver=sensortagdriver.py
    driverparams="hci0 90:59:AF:04:2B:92 $theapp:insensortag"
    removesockets
    startaggregator
    startaggregatorchannel
    startdriver
    startapp
}

function rpidemo {
    aggregatorhost=sulis
    theapp=sensortagapp
    thedriver=sensortagdriver.py
    driverparams="hci0 90:59:AF:04:2B:92 $theapp:insensortag"
    removesockets
    startaggregatorchannel
    startdriver
    startapp
}

function triple {
    aggregatorhost=sulis
    devicehost=bridge-device
    removesockets
    startaggregatorchannel
    startdevicechannel
    startapp
}

function on_exit {
    status=$?
    echo "Exited on command: $BASH_COMMAND Status: $status"
    if [ "$status" != "0" ]; then
        echo "Backtrace:"
        nbt=${#BASH_LINENO[@]}
        for (( i=0; i < $nbt; i++ )); do
            echo " ${FUNCNAME[$i]} line ${BASH_LINENO[$i]}"
        done
    fi

    # Clean up all of the processes
    echo "Cleanup started"
    if [ "${#pids[@]}" != "0" ]; then
        echo "Killing processes"
        # This stops the kill producing an automatic Killed message
        disown -a || true
        for pid in "${pids[@]}"; do
            echo "Killing $pid"
            kill $pid || true
        done
    fi
    lxc-stop -n lxc-$theapp
}

# Must be run as root
if [ "$(id -u)" != "0" ]; then
    echo "This script should be run as 'root'"
    exit 1
fi

if [ "$#" == "1" ]; then
    basedir=$1
else
    basedir=/home/andyduller/Repos/continuum-bridge-proto1
fi
if [ ! -d $basedir ]; then
    echo "$basedir not found"
    exit 1
fi
builddir=$basedir/build
if [ ! -d $builddir ]; then
    echo "$builddir not found"
    exit 1
fi

set -o nounset
set -o errexit

trap 'on_exit' EXIT

# This must agree with the value in aggregator/server.js
aggregatorport=8888
aggregatorhost="192.168.0.15"
deviceport=9999
devicehost=localhost
theserver=printserver.js
theapp=baseapp
thedevice=basedev
pids=()

# Make sure that the /lxc directory exists as a place to put sockets
if [ ! -d /lxc ]; then
    mkdir /lxc
fi

while [ 1 ]; do
    echo "Aggregator host=$aggregatorhost, Port=$aggregatorport"
    echo "Device host=$devicehost, Port=$deviceport"
    echo "App=$theapp Device=$thedevice"
    echo ""
    # List the available functions
    typeset -F | sed -e "s/declare -f//"
    echo -n "Command:"
    read cmd
    # See if the name of a function, in which case just execute it
    if typeset -F | grep "declare -f $cmd$" > /dev/null; then
        $cmd
    else
        case "$cmd" in
            q) exit 0
                ;;
            *) echo "Unknown command $cmd"
                ;;
        esac
    fi
done
