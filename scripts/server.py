#region İmporting Packages

import socket
import threading
import pickle
from settings import *
import struct
from player_info import PlayerInfo, ZombieInfo
from room import Room
from tkinter import Tk, Label, Text, Button, Frame, Entry, BOTH, END
from ctypes import windll
import random

#endregion

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

def set_appwindow(root):
    hwnd = windll.user32.GetParent(root.winfo_id())
    style = windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style = style & ~WS_EX_TOOLWINDOW
    style = style | WS_EX_APPWINDOW
    res = windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
    # re-assert the new window style
    root.withdraw()
    root.after(10, root.deiconify)

class Grip:

    ''' Makes a window dragable. '''
    def __init__ (self, parent, disable=None, releasecmd=None):

        self.parent = parent
        self.root = parent.winfo_toplevel()

        self.disable = disable

        if type(disable) == 'str':

            self.disable = disable.lower()

        self.releaseCMD = releasecmd

        self.parent.bind('<Button-1>', self.relative_position)
        self.parent.bind('<ButtonRelease-1>', self.drag_unbind)

    def relative_position (self, event):

        cx, cy = self.parent.winfo_pointerxy()
        geo = self.root.geometry().split("+")
        self.oriX, self.oriY = int(geo[1]), int(geo[2])
        self.relX = cx - self.oriX
        self.relY = cy - self.oriY

        self.parent.bind('<Motion>', self.drag_wid)

    def drag_wid (self, event):

        cx, cy = self.parent.winfo_pointerxy()
        d = self.disable
        x = cx - self.relX
        y = cy - self.relY

        if d == 'x':

            x = self.oriX

        elif d == 'y':

            y = self.oriY

        self.root.geometry('+%i+%i' % (x, y))

    def drag_unbind (self, event):

        self.parent.unbind('<Motion>')
        
        if self.releaseCMD != None :

            self.releaseCMD()

class Server:

    def __init__(self, application) -> None:
        
        self.application = application

    def PrintLog(self, text: str):

        self.application.PrintLog("[SERVER] => " + text + "\n")

    def Start(self):

        self.isRunning = True
        self.clientSockets = {} # id : clientSocket
        self.roomList = {} # id : playerList
        self.players = {} # playerId : player
        self.zombies = {}

        # Creating a server socket and providing the address family (socket.AF_INET) and type of connection (socket.SOCK_STREAM), i.e. using TCP connection.
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        self.PrintLog("Server is started.")
        
        self.Bind()

    def Bind(self):

        try:

            # Binding the socket with the IP address and Port Number.
            self.server.bind(SERVER_ADDR)

        except socket.error as error:

            self.PrintLog("An error occured during connecting to server: " + str(error))

        else:

            self.PrintLog("Server is binded.")
            self.Listen()

    def Listen(self):

        self.server.listen()
        self.PrintLog(f"Server is listening on IP = {SERVER_IP} at PORT = {SERVER_PORT}")
        playerID, self.roomID = 0, 0

        # running an infinite loop to accept continuous client requests.
        while self.isRunning:

            # Making the server listen to new connections. when a new connection has detected codes will continue 
            try:

                clientSocket, address = self.server.accept()

                playerID += 1

                self.clientSockets[playerID] = clientSocket
                player = PlayerInfo(playerID, address)
                self.players[playerID] = player

                self.PrintLog(f"{player.IP} is connected from PORT = {player.PORT}.")
                self.PrintLog(f"Player count is now {str(len(self.players))}.")

                self.SendData(list(self.players.values()), "!SET_PLAYER_COUNT", len(self.players))

                # starting a new thread
                thread = threading.Thread(target=self.HandleClient, args=(clientSocket, player))
                thread.start()

            except socket.error as e:
            
                if self.isRunning:

                    self.PrintLog(f"Error accepting client connection: {e}")

    def RecieveData(self, clientSocket, player):

        try:

            packedLength = clientSocket.recv(HEADER)
            dataLength = struct.unpack('!I', packedLength)[0]
            serializedData = clientSocket.recv(dataLength)
            return pickle.loads(serializedData)

        except (socket.error, ConnectionResetError):

            self.DisconnectClient(player)

    def SendData(self, playerList, command, value=None, exceptions=[]):

        dataToSend = {'command': command, 'value': value}

        if not hasattr(playerList, '__iter__'):

            playerList = [playerList]

        for exception in exceptions:

            playerList.remove(exception)

        for player in playerList:

            try:

                serializedData = pickle.dumps(dataToSend)
                dataLength = len(serializedData)
                packedLength = struct.pack('!I', dataLength)
                self.clientSockets[player.ID].sendall(packedLength + serializedData)

            except (socket.error, ConnectionResetError):

                self.DisconnectClient(player.ID)
                continue

    def CreateRoom(self):

        self.roomID += 1
        self.roomList[self.roomID] = Room(self.roomID, 4)

    def HandleSpawner(self, room):

        zombieID = 0
        clock = pygame.time.Clock()

        while True:

            now = clock.get_time()
            
            if not hasattr(self, "lastSpawn") or now-self.lastSpawn >= SPAWN_RATE:

                for player in room:

                    zombieID += 1
                    spawnPoint = random.randint(10, 20), random.randint(10, 20)

                    zombie = ZombieInfo(zombieID, room, player.spawnPoint, spawnPoint)
                    self.zombies[zombieID] = zombie
                    self.SendData(room, '!SPAWN', zombie)

                self.lastSpawn = now

    def HandleClient(self, clientSocket: socket.socket, player: PlayerInfo):

        connected = True

        try:

            while connected:
                
                data = self.RecieveData(clientSocket, player)

                if data:

                    command = data['command']
                    value = data['value'] if 'value' in data else None

                    if command == '!SET_PLAYER':
                        
                        playerName, characterName = value
                        player.SetName(playerName)
                        player.SetCharacterName(characterName)
                        self.PrintLog(f"{player.name} ({player.ID}) is entered to lobby.")
                        
                    elif command == '!JOIN_ROOM':

                        roomID = value

                        if len(self.roomList) > 0 and roomID in self.roomList.keys() and self.roomList[roomID].size > len(self.roomList[roomID]):
                            
                            player.JoinRoom(self.roomList[roomID])
                            self.PrintLog(f"{player.name} ({player.ID}) is joined a room {roomID}.")

                            for roomMate in player.room:

                                self.SendData(roomMate, "!SET_ROOM", roomMate)

                        else:

                            self.SendData(player, "!SET_ROOM", False)

                    elif command == '!CREATE_ROOM':

                        self.CreateRoom()
                        player.JoinRoom(self.roomList[self.roomID])
                        self.SendData(player, "!SET_ROOM", player)
                        self.PrintLog(f"{player.name} ({player.ID}) is created a room {self.roomID}.")

                    elif command == '!START_GAME':
                        
                        thread = threading.Thread(target=self.HandleSpawner, args=tuple(player.room))
                        thread.start()
                        self.SendData(player.room, '!START_GAME')

                    elif command == '!SET_PLAYER_RECT':

                        for roomMate in player.room:
                            
                            if roomMate.ID != player.ID:
                               
                                self.SendData(roomMate, command, value)

                    elif command == '!SET_PLAYER_ANGLE':

                        for roomMate in player.room:
                            
                            if roomMate.ID != player.ID:

                                self.SendData(roomMate, command, value)

                    elif command == '!DISCONNECT':
    
                        connected = False
                        self.DisconnectClient(player)

                else:

                    connected = False
        
        except(socket.error, ConnectionResetError):
            
            connected = False
            self.DisconnectClient(player)
        
        finally:

            clientSocket.close()

    def DisconnectClient(self, player: PlayerInfo):
        
        self.clientSockets.pop(player.ID)
        
        if player.room:
            
            if len(player.room) == 1:

                self.roomList.pop(player.room.ID)
            
            else:

                player.room.remove(player)

        self.PrintLog(f"{player.name} ({player.IP}) is dissconnected.")
        self.players.pop(player.ID)
        self.PrintLog(f"Player count is now {str(len(self.players))}.")

        self.SendData(list(self.players.values()), "!DISCONNECT", player.ID)

    def Close(self):

        self.PrintLog(f"Server is closing...")
                
        for player in self.players.values():

            self.DisconnectClient(player)

        self.isRunning = False
        self.server.close()

class Application(Tk):

    def __init__(self):

        super().__init__()

        self.SetWindowTitle(SERVER_TITLE)
        self.SetSize(SERVER_SIZE)
        self.CenterWindow()
        self.MakeUnresizable()
        self.MakeBorderless()
        self.ShowInTaskBar()

        mainFrame = Frame(bg="grey", width= self.width, height=self.height)
        mainFrame.pack_propagate(0)
        mainFrame.pack(fill=BOTH, expand=1)

        topFrame = Frame(mainFrame, bg="#505050")
        topFrame.place(x=0, y=0, anchor="nw", width=self.width, height=40)
        grip = Grip(topFrame)

        Label(topFrame, bg="#505050", fg='white', font=("Comic Sans MS", 15), text=SERVER_TITLE).pack()

        Button(topFrame, text="X", bg="#FF6666", fg="white", command=self.Exit).place(x=self.width-75, y=0, anchor="nw", width=75, height=40)

        Label(mainFrame, text="Command Log", font=("Comic Sans MS", 13)).place(x=20, y=60, anchor="nw")

        self.commandLog = Text(mainFrame, bg='white', fg='green', font=("Comic Sans MS", 12))
        self.commandLog.config(state='disabled')
        self.commandLog.place(x=20, y=110, anchor="nw", width=self.width - 160, height=self.height - 250)

        self.startButton = Button(mainFrame, bg='orange', fg='white', font=("Comic Sans MS", 12), text='START', command=self.StartServer)
        self.startButton.place(x=self.width - 120, y=110, anchor="nw", width=100, height=50)

        self.restartButton = Button(mainFrame, bg='orange', fg='white', font=("Comic Sans MS", 12), text='RESTART', command=self.RestartServer)
        self.restartButton.place(x=self.width - 120, y=170, anchor="nw", width=100, height=50)

        self.closeButton = Button(mainFrame, bg='orange', fg='white', font=("Comic Sans MS", 12), text='CLOSE', command=self.CloseServer)
        self.closeButton.place(x=self.width - 120, y=230, anchor="nw", width=100, height=50)

        Label(mainFrame, text="Command Entry", font=("Comic Sans MS", 13)).place(x=20, y=self.height - 120, anchor="nw")

        self.commandEntry = Entry(mainFrame)
        self.commandEntry.place(x=20, y=self.height - 70, anchor="nw", width=self.width - 160, height=50)

        self.sendButton = Button(mainFrame, bg='orange', fg='white', font=("Comic Sans MS", 12), text='SEND', command=self.SendCommand)
        self.sendButton.place(x=self.width - 120, y=self.height - 70, anchor="nw", width=100, height=50)

        self.startButton["state"] = "normal"
        self.restartButton["state"] = "disabled"
        self.closeButton["state"] = "disabled"
        self.sendButton["state"] = "disabled"

    def Start(self):

        self.mainloop()

    def CenterWindow(self):

        self.update_idletasks()
        width = self.winfo_width()
        frm_width = self.winfo_rootx() - self.winfo_x()
        win_width = width + 2 * frm_width
        height = self.winfo_height()
        titlebar_height = self.winfo_rooty() - self.winfo_y()
        win_height = height + titlebar_height + frm_width
        x = self.winfo_screenwidth() // 2 - win_width // 2
        y = self.winfo_screenheight() // 2 - win_height // 2
        self.geometry('{}x{}+{}+{}'.format(width, height, x, y))
        self.deiconify()

    def ShowInTaskBar(self):

        self.after(10, set_appwindow, self)

    def SetWindowTitle(self, text: str):

        self.wm_title(text)

    def SetSize(self, size):

        self.size = self.width, self.height = size
        self.geometry(str(self.width) + "x" + str(self.height))

    def MakeUnresizable(self):

        self.resizable(0, 0)

    def MakeBorderless(self):

        self.overrideredirect(True)

    def Exit(self):

        self.CloseServer()
        self.destroy()

    def StartServer(self):

        if not hasattr(self, 'server') or not self.server.isRunning:

            self.server = Server(self)
            thread = threading.Thread(target=self.server.Start)
            thread.start()

            self.startButton["state"] = "disabled"
            self.restartButton["state"] = "normal"
            self.closeButton["state"] = "normal"
            self.sendButton["state"] = "normal"

    def SendCommand(self):

        text = self.commandEntry.get()
        command, value = text.split()
        self.server.SendData(self.server.players, command, value)

    def RestartServer(self):

        self.CloseServer()
        self.StartServer()

    def CloseServer(self):

        if hasattr(self, 'server'):

            self.server.Close()

            self.startButton["state"] = "normal"
            self.restartButton["state"] = "disabled"
            self.closeButton["state"] = "disabled"
            self.sendButton["state"] = "disabled"

    def PrintLog(self, text):

        self.commandLog.config(state='normal')
        self.commandLog.insert(END, text)
        self.commandLog.config(state='disabled')
        self.commandLog.yview(END)

if __name__ == '__main__':

    app = Application()
    app.Start()