#!/bin/bash
PATH="/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin"
set -e
CURRENT_DIR=$(dirname $(realpath $0))
AUTOUPDATE_URL=""
VERSION_URL=""
CONTENT_DIR=""
SCRIPT_EXEC=""
EXTRACT_ONLY=0
OUTPUT="./autoextract.sh"
FICHIER_VERSION=""
NEED_ROOT=0
SEND_CALLING_DIR=0
DEBUG=0
COLOR_DEF="\e[0m"
RED="\e[0;31m"
GREEN="\e[0;32m"
BLUE="\e[0;34m"
PURPLE="\e[0;35m"
TAG_SIZE=8
SAVE_CURSOR="\e[s"
RESTORE_CURSOR="\e[u"
CLEAR_LINE="\e[K"
RESET_ROW="\e[1000D"

showReturnedMessage()
{
    showMessage $1 $2 $3
    echo ""
}

showMessage()
{
    if [ $# -ge 3 ]
    then
        textTag=$1
        colorTag=$2
        shift
        shift
        params="$@"
        msg=`echo $params|cut -d"|" -f1`
        infoSup=`echo $params|cut -d"|" -f2 -s`
        nbspace=$((($TAG_SIZE-${#textTag})/2))
        pos=0
        left=""
        while [ $pos -ne $nbspace ]
        do
            pos=$(($pos+1))
            left="$left "
        done
        right=$left
        sum=`echo "$nbspace+${#textTag}+$nbspace"|bc`
        if [ $sum -ne $TAG_SIZE ]
        then
            right="$right "
        fi
        if [ $DEBUG -eq 0 ]
        then
            tag="[$left$colorTag$textTag$right$COLOR_DEF]"
            printf "$CLEAR_LINE$RESET_ROW$tag $msg $RED$infoSup$COLOR_DEF$RESET_ROW"
        else
            tag="[$left$textTag$right]"
            echo -ne "$CLEAR_LINE$RESET_ROW$tag $msg $infoSup$RESET_ROW"
        fi
    else
        echo "Pb de nombre de paramêtres passés à la fonction"
        exit 1
    fi
}

showResult()
{
    resultat=$1
    msg=$2
    if [ $resultat == "0" ]
    then
        textTag="OK"
        colorTag=$GREEN
    else
        textTag="ERREUR"
        colorTag=$RED
    fi
    showReturnedMessage $textTag $colorTag "$msg"
}

showProgress()
{
    pct=$1
    msg=$2
    showReturnedMessage $pct $BLUE $msg
}

showOk()
{
    msg=$1
    showReturnedMessage "OK" $GREEN "$msg"
}

showOK()
{
    msg=$1
    showReturnedMessage "OK" $GREEN "$msg"
}

showError()
{
    msg=$1
    showReturnedMessage "ERREUR" $RED "$msg"
}

showSucces()
{
    msg=$1
    showReturnedMessage "SUCCES" $GREEN "$msg"
}

showInfo()
{
    msg=$1
    showReturnedMessage "INFO" $BLUE "$msg"
}

showAction()
{
    msg=$1
    showReturnedMessage "ACTION" $PURPLE "$msg"
}

Usage(){
    echo "--help                :   Ces lignes"
    echo "--autoupdate url      :   vérifie si une version est disponible a l'url indiquée"
    echo "                          si version pas indiqué, le script téléchargera toujours la"
    echo "                          version distante"
    echo "--version url         :   vérifie dans le fichier indiqué par l'url si la version est"
    echo "                          différente, si oui et autoupdate indiqué alors télécharge la "
    echo "                          nouvelle version et l'exécute"
    echo "--fichier_version nom :   ajoute un fichier version dans le même répertoire que le script à créer"
    echo "--content             :   dossier de contenu à inclure dans le script autoextractable"
    echo "--extract-only        :   décompresse le contenu mais ne lance pas de script"
    echo "--script              :   nom du script contenu dans le dossier défini par content à exécuter une fois"
    echo "                          l'archive décompressée"
    echo "--output              :   nom et chemin du script à créer [defaut=./autoextract.sh]"
    echo "--need_root           :   le script créer devra t'il s'exécuter en root [defaut=non]"
    echo "--send_calling_dir    :   Le script doit il fournir en paramêtre du script le dossier par lequel il est"
    echo "                          lancé [defaut=non]"
    echo "--debug               :   mode debug [defaut=non]"
    exit 1
}

while true
do
    case "$1" in
        --help)
            Usage
            exit 0
        ;;
        --fichier_version)
            shift
            FICHIER_VERSION=$1
            shift
        ;;
        --debug)
            DEBUG=1
            shift
        ;;
        --need_root)
            NEED_ROOT=1
            shift
        ;;
        --extract_only)
            EXTRACT_ONLY=1
            shift
        ;;
        --autoupdate)
            shift
            AUTOUPDATE_URL=$1
            shift
        ;;
        --version)
            shift
            VERSION_URL=$1
            shift
        ;;
        --content)
            shift
            CONTENT_DIR=$1
            shift
        ;;
        --script)
            shift
            SCRIPT_EXEC=$1
            shift
        ;;
        --output)
            shift
            OUTPUT=$1
            shift
        ;;
        --send_calling_dir)
            shift
            SEND_CALLING_DIR=1
        ;;
        *)
            break
        ;;
    esac
done

SCRIPT_NAME=$(basename $OUTPUT)
if test $DEBUG -eq 1;then
showInfo "Mode Debug actif"
echo "AUTOUPDATE_URL:$AUTOUPDATE_URL"
echo "VERSION_URL:$VERSION_URL"
echo "CONTENT_DIR:$CONTENT_DIR"
echo "SCRIPT_EXEC:$SCRIPT_EXEC"
echo "EXTRACT_ONLY:$EXTRACT_ONLY"
echo "OUTPUT:$OUTPUT"
echo "FICHIER_VERSION:$FICHIER_VERSION"
echo "NEED_ROOT:$NEED_ROOT"
echo "SEND_CALLING_DIR:$SEND_CALLING_DIR"
set -xve
fi

if [ -z "$CONTENT_DIR" ];then
    showError "Informations nécessaires non définies"
    Usage
    exit 1
fi
if [ -z "$SCRIPT_EXEC" ];then
    if test $EXTRACT_ONLY -ne 1; then
        showError "Le script à executer ou le mode extract_only doivent être sélectionné"
        Usage
        exit 1
    fi
fi

if test $DEBUG -eq 0;then
    tmp=`mktemp -d "/tmp/$SCRIPT_NAME.XXX"`
else
    tmp=`mktemp -d "$CURRENT_DIR/$SCRIPT_NAME.XXX"`
fi

NUM_VERSION=`date +%Y%m%d%H%M%S`
showInfo "Numéro de version =>|$NUM_VERSION"

if [ ! -z $FICHIER_VERSION ]
then
    echo $NUM_VERSION > $FICHIER_VERSION
fi

showAction "Compression des fichiers"
cd $CONTENT_DIR
tar -cf  "$tmp/include.tar" * --no-same-owner --no-same-permissions
if test $DEBUG -eq 1;then
    tar --list -f $tmp/include.tar
fi

cd $tmp

gzip include.tar
cat << EOT >> decompress
#!/bin/sh
PATH="/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin"
SCRIPT_NAME=\$(basename \$0)
CURRENT_DIR=\$(dirname \$(realpath \$0))
SEND_CALLING_DIR=%SEND_CALLING_DIR%
NO_UPDATE=0
EXTRACT_ONLY=%EXTRACT_ONLY%
EXTRACT_ONLY_FORCE=0
VERSION_URL="%VERSION_URL%"
AUTOUPDATE_URL="%AUTOUPDATE_URL%"
NUM_VERSION="%NUM_VERSION%"
SCRIPT_EXEC="%SCRIPT_EXEC%"
NB_LIGNES="%NB_LIGNES%"
NEED_ROOT="%NEED_ROOT%"
MODE_DEBUG="%MODE_DEBUG%"
DEBUG=0
PARAMS="\$@"
COLOR_DEF="\e[0m"
RED="\e[0;31m"
GREEN="\e[0;32m"
BLUE="\e[0;34m"
PURPLE="\e[0;35m"
TAG_SIZE=8
SAVE_CURSOR="\e[s"
RESTORE_CURSOR="\e[u"
CLEAR_LINE="\e[K"
RESET_ROW="\e[1000D"

showReturnedMessage()
{
    showMessage \$1 \$2 \$3
    echo ""
}

showMessage()
{
    if [ \$# -ge 3 ]
    then
        textTag=\$1
        colorTag=\$2
        shift
        shift
        params="\$@"
        msg=\`echo \$params|cut -d"|" -f1\`
        infoSup=\`echo \$params|cut -d"|" -f2 -s\`
        nbspace=\$(((\$TAG_SIZE-\${#textTag})/2))
        pos=0
        left=""
        while [ \$pos -ne \$nbspace ]
        do
            pos=\$((\$pos+1))
            left="\$left "
        done
        right=\$left
        sum=\`echo "\$nbspace+\${#textTag}+\$nbspace"|bc\`
        if [ \$sum -ne \$TAG_SIZE ]
        then
            right="\$right "
        fi
        if [ \$DEBUG -eq 0 ]
        then
            tag="[\$left\$colorTag\$textTag\$right\$COLOR_DEF]"
            printf "\$CLEAR_LINE\$RESET_ROW\$tag \$msg \$RED\$infoSup\$COLOR_DEF\$RESET_ROW"
        else
            tag="[\$left\$textTag\$right]"
            echo -ne "\$CLEAR_LINE\$RESET_ROW\$tag \$msg \$infoSup\$RESET_ROW"
        fi
    else
        echo "Pb de nombre de paramêtres passés à la fonction"
        exit 1
    fi
}

showResult()
{
    resultat=\$1
    msg=\$2
    if [ \$resultat == "0" ]
    then
        textTag="OK"
        colorTag=$GREEN
    else
        textTag="ERREUR"
        colorTag=$RED
    fi
    showReturnedMessage \$textTag \$colorTag "\$msg"
}

showProgress()
{
    pct=\$1
    msg=\$2
    showReturnedMessage \$pct \$BLUE \$msg
}

showOk()
{
    msg=\$1
    showReturnedMessage "OK" \$GREEN "\$msg"
}

showOK()
{
    msg=\$1
    showReturnedMessage "OK" \$GREEN "\$msg"
}

showError()
{
    msg=\$1
    showReturnedMessage "ERREUR" \$RED "\$msg"
}

showSucces()
{
    msg=\$1
    showReturnedMessage "SUCCES" \$GREEN "\$msg"
}

showInfo()
{
    msg=\$1
    showReturnedMessage "INFO" \$BLUE "\$msg"
}

showAction()
{
    msg=\$1
    showReturnedMessage "ACTION" \$PURPLE "\$msg"
}

Usage(){
    echo "--help                :   Ces lignes"
    echo "--no_update           :   Pas de vérification et de lancement de la nouvelle version même"
    echo "                      :   si à l'origine le programme le prévoit"
    echo "--extract_only        :   Extrait les fichiers mais ne lance pas le script après implique --no_update"
    echo "--debug               :   mode debug [defaut=non]"
}

MODE_DEBUG=""

while true
do
    case "\$1" in
        --help)
            Usage
            exit 0
        ;;
        --no_update)
            NO_UPDATE=1
            shift
        ;;
        --debug)
            DEBUG=1
            MODE_DEBUG="--debug"
            shift
        ;;
        --extract_only)
            EXTRACT_ONLY_FORCE=1
            shift
        ;;
        *)
            break
        ;;
    esac
done

if test \$DEBUG -eq 1;then
    showInfo "Mode Debug actif"
    echo "SCRIPT_NAME:\$SCRIPT_NAME"
    echo "CURRENT_DIR:\$CURRENT_DIR"
    echo "NO_UPDATE:\$NO_UPDATE"
    echo "EXTRACT_ONLY:\$EXTRACT_ONLY"
    echo "EXTRACT_ONLY_FORCE:\$EXTRACT_ONLY_FORCE"
    echo "VERSION_URL:\$VERSION_URL"
    echo "AUTOUPDATE_URL=\$AUTOUPDATE_URL"
    echo "NUM_VERSION:\$NUM_VERSION"
    echo "SEND_CALLING_DIR:\$SEND_CALLING_DIR"
    echo "NB_LIGNES:\$NB_LIGNES"
    echo "NEED_ROOT:\$NEED_ROOT"
    echo "DEBUG:\$DEBUG"
    set -xv
fi

if [ \$EXTRACT_ONLY -eq 1 ] || [ \$EXTRACT_ONLY_FORCE -eq 1 ]
then
    NO_UPDATE=1
fi


if [ ! "\$BASH_VERSION" ]
then
    showAction "Redémarrage via Bash"
    /bin/bash "\$0" \$PARAMS
    exit \$?
fi

if test \$NEED_ROOT -eq 1;then
    IDuser=\`id -u\`
    if [ \$IDuser -ne 0 ]
    then
        showAction "Redémarrage en root"
        /usr/bin/sudo /bin/bash "\$0" \$PARAMS
        exit \$?
    fi
fi

if [ \$DEBUG -eq 1 ] || [ \$EXTRACT_ONLY -eq 1 ] || [ \$EXTRACT_ONLY_FORCE -eq 1 ]
then
    tmp=\`mkdir -p "./\$SCRIPT_NAME.extract"\`
    tmp="\$CURRENT_DIR/\$SCRIPT_NAME.extract"
else
    tmp=\`mktemp -d "/tmp/\$SCRIPT_NAME.XXX"\`
fi

cd \$tmp
if [ \$NO_UPDATE -eq 0  ]
then
    DOWNLOAD=1
    if [ ${#VERSION_URL} -ne 0 ]
    then
        showAction "Vérification de la version distante"
        if [ \$NEED_ROOT -eq 1 ]
        then
            chmod 777 version 2>>/dev/null
        fi
        wget -t 1 -q --show-progress --progress=bar:force -T 5 \$VERSION_URL -O version 2>&1
        if [ \$? -eq 0 ]
        then
            chmod 777 version 2>>/dev/null
            DL_VERSION=\`cat version\`
            showInfo "Version en cours : \$NUM_VERSION| Version distante: \$DL_VERSION"
            if [ \$DL_VERSION -gt \$NUM_VERSION ]
            then
                showAction "Téléchargement de la nouvelle version disponible"
            else
                DOWNLOAD=0
            fi
        else
            showError "Impossible de vérifier la présence d'une nouvelle version|On continue avec la version en cours"
            DOWNLOAD=0
        fi
    else
        showMessage "ACTION" \$PURPLE "Téléchargement de la version distante"
        DOWNLOAD=0
    fi
    if [ \$DOWNLOAD -eq 1 ]
    then
        wget -t 1 -q --show-progress --progress=bar -T 5 \$AUTOUPDATE_URL -O newScript.sh
        if [ \$? -eq 0 ]
        then
            showOk "Fichier Télécharger avec succès"
            mv newScript.sh \$CURRENT_DIR/\$SCRIPT_NAME
            chmod 777 \$CURRENT_DIR/\$SCRIPT_NAME
        cd $CURRENT_DIR
            /bin/bash \$CURRENT_DIR/\$SCRIPT_NAME \$PARAMS
            exit \$?
        else
            showError "Echec du téléchargement|L'ancien script va être utilisé"
        fi
    fi
else
    if [ ! -z AUTOUPDATE_URL ]
    then
        showInfo "Pas de vérification d'une nouvelle version comme demandé"
    fi
fi

COMPLETE_ROOT="\$CURRENT_DIR/\$SCRIPT_NAME"
tail -n+\$NB_LIGNES \$COMPLETE_ROOT >archive.tar.gz
showAction "Décompression des fichiers"
tar xf archive.tar.gz
rm archive.tar.gz
cd \$CURRENT_DIR

CALLING_DIR=""
EXTRACT_DIR="--extract_dir \$tmp"
if test $SEND_CALLING_DIR -eq 1;then
    CALLING_DIR="--calling_dir \$CURRENT_DIR"
fi
if [ \$EXTRACT_ONLY -eq 0 ] && [ \$EXTRACT_ONLY_FORCE -eq 0 ]
then
    showAction "Lancement de \$SCRIPT_EXEC"
    cd \$tmp
    bash \$tmp/\$SCRIPT_EXEC \$CALLING_DIR \$EXTRACT_DIR \$MODE_DEBUG
else
    showInfo "Les fichiers sont dans|\$tmp"
fi
exit 0
__ARCHIVE_BELOW__
EOT

sed -i "s|%EXTRACT_ONLY%|$EXTRACT_ONLY|g" decompress
sed -i "s|%VERSION_URL%|$VERSION_URL|g" decompress
sed -i "s|%AUTOUPDATE_URL%|$AUTOUPDATE_URL|g" decompress
sed -i "s|%NUM_VERSION%|$NUM_VERSION|g" decompress
sed -i "s|%SCRIPT_EXEC%|$SCRIPT_EXEC|g" decompress
sed -i "s|%NEED_ROOT%|$NEED_ROOT|g" decompress
sed -i "s|%MODE_DEBUG%|$MODE_DEBUG|g" decompress
sed -i "s|%SEND_CALLING_DIR%|$SEND_CALLING_DIR|g" decompress
NB_LIGNES=`awk '/^__ARCHIVE_BELOW__/ {print NR + 1; exit 0; }' decompress`
sed -i "s|%NB_LIGNES%|$NB_LIGNES|g" decompress
cat decompress include.tar.gz > $SCRIPT_NAME
if test $DEBUG -eq 1;then
    echo $tmp
fi
showAction "Finalisation du script"
cp $SCRIPT_NAME $CURRENT_DIR/$SCRIPT_NAME
showOK      "Script créé avec succès"
exit 0