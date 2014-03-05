#!/bin/bash

echo_and_run() { echo "$@" ; "$@" ; } 

ask_exit() {
    read -n 1 -r -p "$1"
    echo -e "\n"
    if [[ $REPLY =~ ^[Yy]$ ]]
    then
            return 0;
    else
            echo "Abort.."
            exit
    fi  
}

ask() {
    read -n 1 -r -p "$1"
    echo -e "\n"
    if [[ $REPLY =~ ^[Yy]$ ]]
    then
        return 0;
    else
        return 1;
    fi  
}

setup_wifi() {
    echo -e "Enter the SSID:"
    read SSID
    echo -e "Enter the WPA Shared Key:"
    read WPASK
    sudo cat > /etc/wpa_supplicant/wpa_supplicant.conf << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
network={
    ssid="${SSID}"
    proto=RSN
    key_mgmt=WPA-PSK
    pairwise=CCMP 
    TKIPgroup=CCMP 
    TKIPpsk="${WPASK}"
}
EOF
    sudo cat > /etc/network/interfaces << EOF
auto lo
iface lo inet loopback
iface eth0 inet dhcp
auto wlan0
allow-hotplug wlan0
iface wlan0 inet dhcp
wireless-essid myssid
wpa-roam /etc/wpa_supplicant/wpa_supplicant.conf
iface default inet dhcp
EOF
    sudo ifdown wlan0
    sudo ifup wlan0
}

## Script Start ##

sudo apt-get install -y rpi-update
sudo apt-get update -y
sudo apt-get upgrade -y

if ask "Would you like to setup the WiFi? You will need an SSID and WPA Shared Key for the network [y/N]"; then
    echo "Set up the WiFi please"
    setup_wifi
else
    echo "No thanks to the WiFi"
fi

sudo apt-get install -y vim

# From Andy's notes
sudo apt-get install -y lxc
sudo apt-get install -y busybox-static
sudo apt-get install -y swig

sudo apt-get install -y python-dev
sudo apt-get install -y python-pip
sudo apt-get install -y python-software-properties
sudo apt-get install -y nodejs npm node-semver
sudo apt-get install -y python-pexpect

sudo apt-get install python-twisted

# For Bluetooth LE
sudo apt-get install -y libglib2.0-dev 
sudo apt-get install -y libdbus-1-dev 
sudo apt-get install -y libusb-dev 
sudo apt-get install -y libudev-dev 
sudo apt-get install -y libical-dev
sudo apt-get install -y systemd 
sudo apt-get install -y libreadline-dev

mkdir /home/bridge/src
cd /home/bridge/src
wget https://www.kernel.org/pub/linux/bluetooth/bluez-5.5.tar.gz
tar xvfz bluez-5.5.tar.gz
cd bluez-5.5.tar.gz
./configure --prefix=/usr --mandir=/usr/share/man --sysconfdir=/etc --localstatedir=/var --disable-systemd
sudo make
sudo make install

# sqlite front-end
pip install dataset
