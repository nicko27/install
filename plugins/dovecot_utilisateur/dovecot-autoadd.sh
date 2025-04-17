pkill thunderbird
ServDovecot="%%DOVECOT_SMS%%"
dc_param() {
	cle=$1
	fic_js=$2
	echo "$(grep $cle $fic_js |sed -e "s|user_pref.*$cle[^,]*,[ \t]*\(.*\));|\1|g" -e "s|\"\(.*\)\"|\1|g" | head -n1)"
}

AjoutDovecot()
{
	for nomUt in `ls /home|grep -v lost+found`;do
		dir="/home/$nomUt"
		if [ -d "$dir/.thunderbird" ]
		then
			for eltThu in `ls $dir/.thunderbird|grep -v "profiles.ini"|grep -v "Crash Reports"`;do
				nomThuPrefsJS="$dir/.thunderbird/$eltThu/prefs.js"
				if [ -f "$nomThuPrefsJS" ]
				then
					compteActifs=$(dc_param mail.accountmanager.accounts $nomThuPrefsJS)
					echo "compteActifs:$compteActifs"
					compteur=$(dc_param mail.account.lastKey $nomThuPrefsJS)
					paramJSOK=`cat $nomThuPrefsJS|grep "mail.server.default.using_subscription"|grep -c "false"`
					paramJSDovecot=`cat "$nomThuPrefsJS"|grep -c "Dossiers_Locaux_Unites_via_Dovecot"`
					paramLF=0
					for numero in $(seq 1 $compteur);do
						echo "numero:mail.server.server${numero}.type"
						typeCompte=$(dc_param mail.server.server${numero}.type $nomThuPrefsJS)
						echo "typeCompte:$typeCompte"
						if [ "$typeCompte" == "none" ]
						then
							destCompte=$(dc_param mail.server.server${numero}.directory $nomThuPrefsJS)
							echo "destCompte:$destCompte"
							nbRzo=`echo "$destCompte"|grep travail|grep -c "smb-share"`
							echo "nbRzo:$nbRzo"
							if [ $nbRzo -eq 0 ]
							then
								nameAccount="account${numero}"
								echo "nameAccount:$nameAccount"
								accountVisible=`echo $compteActifs|grep -c $nameAccount`
								echo "accountVisible=$accountVisible"
								if [ $accountVisible -ne 0 ]
								then
									paramLF=$compteur
								fi
								echo "paramLF=$paramLF"
							else
								titreCompte=$(dc_param mail.server.server${numero}.name $nomThuPrefsJS)
								inactif=`echo $titreCompte|grep -c inactif_appeler_SOLC`
								if [ $inactif -eq 0 ]
								then
									echo "user_pref(\"mail.server.server${numero}.name\", \"${titreCompte} inactif_appeler_SOLC\");" >> $nomThuPrefsJS
								fi
							fi
						fi
					done
					echo "PasAjoutCompte:$paramLF"
					if [ $paramLF -eq 0 ]
					then
						compteur=$(($compteur+1))
						echo "user_pref(\"mail.server.server${compteur}.directory\", \"$dir/.thunderbird/$eltThu/Mail/Local Folders\");
						user_pref(\"mail.server.server${compteur}.directory-rel\", \"[ProfD]Mail/Local Folders\");
						user_pref(\"mail.server.server${compteur}.hostname\", \"Dossiers Perso\");
						user_pref(\"mail.server.server${compteur}.name\", \"Dossiers Perso\");
						user_pref(\"mail.server.server${compteur}.storeContractID\", \"@mozilla.org/msgstore/berkeleystore;1\");
						user_pref(\"mail.server.server${compteur}.type\", \"none\");
						user_pref(\"mail.account.account${compteur}.server\", \"server${compteur}\");
						user_pref(\"mail.server.server${compteur}.userName\", \"nobody\");"  >> $nomThuPrefsJS

						old_accounts=$(dc_param mail.accountmanager.accounts $nomThuPrefsJS)
						accounts="$old_accounts,account$compteur"
						sed -i "s|^user_pref(\"mail.accountmanager.accounts\",[ \t]*.*);|user_pref(\"mail.accountmanager.accounts\", \"$accounts\");|g" $nomThuPrefsJS
						sed -i "s|^user_pref(\"mail.account.lastKey\",[ \t]*.*);|user_pref(\"mail.account.lastKey\", $compteur);|g" $nomThuPrefsJS
					fi
                    if [ $paramLF -ne 0 ]
                    then
                        echo "ici"
                    fi
					if [ $paramJSOK -eq 1 ]
					then
						echo ""
					else
						echo "user_pref(\"mail.server.default.using_subscription\", false);" >> $nomThuPrefsJS
					fi
					if [ $paramJSDovecot -eq 0 ]
					then
						compteur=$(($compteur+1))
						echo "user_pref(\"mail.account.account${compteur}.identities\", \"id${compteur}\");
						user_pref(\"mail.account.account${compteur}.server\", \"server${compteur}\");
						user_pref(\"mail.server.server${compteur}.cacheCapa.acl\", true);
						user_pref(\"mail.server.server${compteur}.cacheCapa.quota\", false);
						user_pref(\"mail.server.server${compteur}.check_new_mail\", true);
						user_pref(\"mail.server.server${compteur}.delete_model\",  2);
						user_pref(\"mail.server.server${compteur}.directory\", \"${default_dir}/${ServDovecot}\" );
						user_pref(\"mail.server.server${compteur}.directory-rel\", \"[ProfD]ImapMail/${ServDovecot}\");
						user_pref(\"mail.server.server${compteur}.force_select\", \"no-auto\");
						user_pref(\"mail.server.server${compteur}.hostname\", \"${ServDovecot}\");
						user_pref(\"mail.server.server${compteur}.login_at_startup\", true);
						user_pref(\"mail.server.server${compteur}.max_cached_connections\", 5);
						user_pref(\"mail.server.server${compteur}.name\", \"Dossiers Locaux Unite\");
						user_pref(\"mail.server.server${compteur}.namespace.personal\", \"\\\"\\\"\");
						user_pref(\"mail.server.server${compteur}.port\", 993);
						user_pref(\"mail.server.server${compteur}.serverIDResponse\", \"(\\\"name\\\" \\\"Dovecot\\\")\");
						user_pref(\"mail.server.server${compteur}.socketType\", 3);
						user_pref(\"mail.server.server${compteur}.spamActionTargetAccount\", \"imap://${nomUt}@${ServDovecot}\");
						user_pref(\"mail.server.server${compteur}.storeContractID\", \"@mozilla.org/msgstore/berkeleystore;1\");
						user_pref(\"mail.server.server${compteur}.timeout\", 29);
						user_pref(\"mail.server.server${compteur}.type\", \"imap\");
						user_pref(\"mail.identity.id${compteur}.organization\", \"Dossiers_Locaux_Unites_via_Dovecot (ne pas effacer ou modifier cette ligne)\");
						user_pref(\"mail.server.server${compteur}.userName\", \"${nomUt}\");" >> $nomThuPrefsJS
						old_accounts=$(dc_param mail.accountmanager.accounts $nomThuPrefsJS)
						accounts="$old_accounts,account$compteur"
						sed -i "s|^user_pref(\"mail.accountmanager.accounts\",[ \t]*.*);|user_pref(\"mail.accountmanager.accounts\", \"$accounts\");|g" $nomThuPrefsJS
						sed -i "s|^user_pref(\"mail.account.lastKey\",[ \t]*.*);|user_pref(\"mail.account.lastKey\", $compteur);|g" $nomThuPrefsJS
						default_account=$(dc_param mail.accountmanager.defaultaccount $nomThuPrefsJS)
						default_account_num=`echo "$default_account"|cut -d"t" -f2`
						showSignature=$(dc_param mail.identity.id$default_account_num.attach_signature $nomThuPrefsJS);

						if [ "$showSignature" == "true" ]
						then
							sign=$(dc_param mail.identity.id$default_account_num.sig_file $nomThuPrefsJS)
							echo "user_pref(\"mail.identity.id$compteur.sig_file\", \"$sign\");" >> $nomThuPrefsJS
							sign=$(dc_param mail.identity.id$default_account_num.sig_file-rel $nomThuPrefsJS)
							echo "user_pref(\"mail.identity.id$compteur.sig_file-rel\", \"$sign\");" >> $nomThuPrefsJS
							echo "user_pref(\"mail.identity.id$compteur.attach_signature\", true);" >> $nomThuPrefsJS
						fi
						showHtml=$(dc_param mail.identity.id$default_account_num.htmlSigFormat $nomThuPrefsJS)
						if [ -z $showHtml ]
						then
							showHtml=false
						fi
						echo "user_pref(\"mail.identity.id$compteur.htmlSigFormat\", $showHtml);" >> $nomThuPrefsJS
						textSignature=$(dc_param mail.identity.id$default_account_num.htmlSigText $nomThuPrefsJS)
						echo "user_pref(\"mail.identity.id$compteur.htmlSigText\", \"$textSignature\");" >>$nomThuPrefsJS

					fi
				fi
			done
		fi

	done
}


if [ "$BASH_VERSION" ]
then
    AjoutDovecot
else
    exec /bin/bash "$0"
fi