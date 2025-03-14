#!/usr/bin/env python3
"""
Script d'initialisation d'un ESC pour moteur brushless
À exécuter une fois avant d'utiliser l'API

Ce script effectue la séquence d'armement standard pour les ESC de moteurs brushless.
Cela calibre l'ESC pour qu'il reconnaisse les signaux min et max.
"""

import RPi.GPIO as GPIO
import time
import sys

# Configuration
ESC_PIN = 23  # GPIO23 (broche 16)
FREQUENCY = 50  # Hz (standard pour les ESC)
MIN_DUTY = 5    # Généralement 5% pour un signal de 1ms
MAX_DUTY = 10   # Généralement 10% pour un signal de 2ms

# Mode automatique si lancé avec l'argument --auto
AUTO_MODE = "--auto" in sys.argv

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(ESC_PIN, GPIO.OUT)
esc = GPIO.PWM(ESC_PIN, FREQUENCY)
esc.start(0)

def wait_for_input(message):
    if AUTO_MODE:
        print(message + " (mode automatique, continue après 3 secondes)")
        time.sleep(3)
        return
    else:
        input(message)

try:
    print("Programme d'initialisation d'ESC")
    
    if AUTO_MODE:
        print("Mode automatique activé - ASSUREZ-VOUS QUE LA BATTERIE EST DÉJÀ CONNECTÉE")
    else:
        print("IMPORTANT: Assurez-vous que la batterie est connectée à l'ESC!")
    
    wait_for_input("Appuyez sur Enter pour continuer...")
    
    print("Envoi du signal minimum...")
    esc.ChangeDutyCycle(0)
    time.sleep(2)
    
    print("Envoi du signal d'armement...")
    esc.ChangeDutyCycle(MAX_DUTY)
    time.sleep(2)
    
    print("Retour au signal neutre...")
    esc.ChangeDutyCycle(MIN_DUTY)
    time.sleep(2)
    
    print("Signal d'arrêt...")
    esc.ChangeDutyCycle(0)
    time.sleep(1)
    
    print("ESC initialisé et armé avec succès")
    
    if not AUTO_MODE:
        print("Test du moteur? (o/n)")
        test = input().lower()
        if test == 'o' or test == 'oui':
            print("Test de démarrage moteur à vitesse minimale...")
            esc.ChangeDutyCycle(MIN_DUTY + 0.5)  # Légèrement au-dessus du minimum
            time.sleep(2)
            print("Arrêt moteur")
            esc.ChangeDutyCycle(0)
    
    print("Initialisation terminée!")

except KeyboardInterrupt:
    print("Opération annulée par l'utilisateur")

finally:
    esc.stop()
    GPIO.cleanup()
    print("Programme terminé")