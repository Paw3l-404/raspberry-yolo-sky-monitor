# raspberry-yolo-sky-monitor
 Głównym celem projektu inżynierskiego jest stworzenie taniego, energooszczędnego i niezależnego stanowiska obserwacyjnego. System pozwala na bezobsługowe nagrywanie nocnego nieba oraz autonomiczną analizę materiału w celu identyfikacji przelotów meteorów oraz innych obiektów kosmicznych. 

📌 Krótki opis projektu
System automatycznego monitorowania nocnego nieba oparty na komputerze jednopłytkowym Raspberry Pi oraz algorytmach sztucznej inteligencji. Projekt automatyzuje proces ciągłej rejestracji obrazu oraz detekcji zjawisk astronomicznych (ze szczególnym uwzględnieniem meteorów) przy wykorzystaniu architektury sieci neuronowych YOLO (You Only Look Once) oraz autorskiego zbioru danych wizyjnych.


🛠️ Architektura i stos technologiczny
Projekt integruje rozwiązania z zakresu hardware'u oraz inżynierii danych:

Hardware: Raspberry Pi + dedykowany moduł kamery (IMX462).

Computer Vision & AI: Modele z rodziny YOLO do błyskawicznej detekcji obiektów (Object Detection).

Przetwarzanie danych (Data Engineering): Platforma Roboflow wykorzystywana do iteracyjnego budowania zbioru danych, wersjonowania oraz augmentacji obrazu.

Skrypty systemowe: Python (obsługa logiki i kamery) oraz powłoka Bash/FFmpeg
