
sudo adduser bridge

USER="bridge"
PASSWORD="t00f@r"

echo -e "$PASSWORD\n$PASSWORD\n" | sudo passwd $user

sudo useradd bridge sudo
sudo useradd bridge adm

echo -e "$PASSWORD\n" | su bridge
