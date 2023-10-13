import chess
import chess.pgn
import pygame
import os
import time
import math
import socket
import struct
import unidecode
import json
import webbrowser
import random
from datetime import datetime
from networking import make_packet, Client, Server

"""                                       
                *(##%&                  
              ((////((#&                
             ///,***//(#&               
              ////////(%*               
                ****/(.                 
               ******/(&                
              /*,,,,**@@@               
             .**,,,*/*&@%/.             
  ,,,,**,,,,*,**,,,*&&&&&&%//***////    
  ,,,,,,,,,*,,**,,,**&@@@&/(*//*////    
    .,**/********,**%#@@@@*///,         
              /**,,.,%@@@%.             
              /*****/&@@@@              
     .**,(###*/*/#%%%&@@@@              
     *,*((#%.#/ /   ##@@ %%             
    ,/.///(///**,,,,,,./,(,.....(/.     
    ,/,*///*/******,,,*/*,/....//#(/*.* 
     ****//(/(   &@@@@,*,**,...*/*.*/,  
       ,,&%//   /@@@@@@@@@@@@@(,#       
          //              /#@           
         (/                (#           
         /                  #           
"""

GUI_BTN_PAD = 8
GUI_BTN_OUTLINE_W = 3

class GuiButton:
    def __init__(self, pos, content, normal_clr=(0, 196, 0), pressed_clr=(169, 128, 0), min_w=300):
        self.pos = pos
        
        self.content = content
        self.c_w,self.c_h = self.content.get_size()
        self.rect = pygame.Rect(0, 0, max(self.c_w+(GUI_BTN_PAD)*2, min_w), self.c_h+GUI_BTN_PAD*2)
        
        self.hover = False
        self.pressed = False

        self.normal_clr = normal_clr
        self.pressed_clr = pressed_clr

        self.set_pos(self.pos)

    def set_pos(self, pos):
        self.pos = pos
        self.rect.x = self.pos[0]
        self.rect.y = self.pos[1]

    def draw(self, screen):
        screen.fill((0, 0, 0), self.rect.inflate(GUI_BTN_OUTLINE_W, GUI_BTN_OUTLINE_W))
        screen.fill(self.pressed_clr if self.hover else self.normal_clr, self.rect)
        screen.blit(self.content, transform(center((self.rect.w, self.rect.h), (self.c_w, self.c_h)), self.pos))

    def update(self, events, mouse_pos):
        self.hover = False
        self.pressed = False
        if self.rect.collidepoint(mouse_pos):
            self.hover = True

            for e in events:
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if e.button == pygame.BUTTON_LEFT:
                        self.pressed = True

ENTRY_TYPE_TEXT = 0
ENTRY_TYPE_NUM = 1
ENTRY_TYPE_IP = 2
class GuiEntry:
    def __init__(self, pos, font, initial_text="", max_length=12, min_w=300, _type=ENTRY_TYPE_TEXT):
        self.pos = pos
        
        self.font = font
        self.max_length = max_length
        self.h = self.font.get_height() + GUI_BTN_PAD * 2
        self.w = max(min_w, self.font.size("a"*self.max_length)[0] + GUI_BTN_PAD * 2)

        self.rect = pygame.Rect(*self.pos, self.w, self.h)

        self.input = initial_text
        self.focus = False

        self.type = _type

        self.blink = 0

        self.set_pos(self.pos)

    def set_focus(self, f):
        if type(f) == bool:
            self.focus = f

    def set_pos(self, pos):
        self.pos = pos
        self.rect.x = self.pos[0]
        self.rect.y = self.pos[1]

    def set_input(self, text):
        self.input = text

    def get(self):
        return self.input

    def update(self, events, mouse_pos):
        pressed = False
        for e in events:
            if e.type == pygame.KEYDOWN and self.focus:
                if e.unicode.isprintable():
                    char = e.unicode
    
                    if len(self.input) < self.max_length:
                        if self.type == ENTRY_TYPE_NUM:
                            if char.isdigit():
                                self.input += char
                        if self.type == ENTRY_TYPE_IP:
                            if char.isdigit() or char in [".", ":"]:
                                self.input += char
                        if self.type == ENTRY_TYPE_TEXT:
                            self.input += char
                if e.key == 8:
                    self.input = self.input[0:-1]
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == pygame.BUTTON_LEFT:
                pressed = self.rect.collidepoint(mouse_pos)
        return pressed

    def draw(self, screen):
        text_surf = self.font.render(self.input, True, (0, 0, 0))

        if self.focus:
            screen.fill((196, 196, 0), self.rect.inflate(GUI_BTN_OUTLINE_W*2, GUI_BTN_OUTLINE_W*2))

        screen.fill((0, 0, 0), self.rect.inflate(GUI_BTN_OUTLINE_W, GUI_BTN_OUTLINE_W))
        screen.fill((160, 160, 160), self.rect)

        screen.blit(text_surf, transform(self.pos, (GUI_BTN_PAD, GUI_BTN_PAD)))

        if self.blink %20 > 10:
            if self.focus:
                screen.fill((255, 255, 255), pygame.Rect(self.pos[0]+text_surf.get_size()[0]+5, self.pos[1], 5, self.h-5))
        self.blink += 1

class EntryFocusManager:
    def __init__(self, entries):
        self.entries = entries
        self.idx = 0
        self.focus_to_idx(self.idx)

    def focus_to_idx(self, i):
        self.idx = i
        for entry in self.entries:
            entry.set_focus(False)

        self.entries[self.idx].set_focus(True)

    def update(self, events, mouse_pos):
        for i,e in enumerate(self.entries):
            if e.update(events, mouse_pos): ## clicked
                self.focus_to_idx(i)
                return

STATUS_NOT_CONNECTED = -1 ## only for client
STATUS_WAITING_FOR_PLAYERS = 0
STATUS_PLAYING = 1
STATUS_GAME_ENDED = 2
STATUS_GAME_ENDED_PLAYER_LEFT = 3
STATUS_SERVER_STOPPED = 4

UTIL_STATUS_HUMAN_READABLE = ["Waiting for opponent!", "Game", "Game ended!", "Opponent left!", "Server shutting down!", "Connection lost!"]

def write_utf8_string(string):
    buf = string.encode("utf-8")

    return struct.pack("I", len(buf)) + buf

def read_utf8_string(buf):
    l = struct.unpack("I", buf[0:4])[0]

    return buf[4:4+l].decode("utf-8")
    
PACKET_STATUS = 2               ## int8 status
PACKET_SET_NICK = 3             ## utf8_string nick
PACKET_PLAYER_INFO = 4          ## int8 idx, utf8_string nick
PACKET_SIDE = 5                 ## int8 side
PACKET_BOARD = 6                ## int8 is_capture utf8_string board_epd
PACKET_GIVE_UP = 7              ## give up
PACKET_MOVE = 8                 ## int8 from, int8 to
PACKET_GAME_OUTCOME = 9         ## int8 termination, int8 winner
PACKET_CLIENT_MOVE_INFO = 10    ## int8 from, int8 to               info for client to see what was moved
PACKET_CLIENT_TAKEN_INFO = 11   ## int8 piece                       info for client to see what was taken

OUTCOME_RESIGNED = 11
## this server should accept two clients
## and then start the game
class ChessServer:
    ##
    ## Server
    ##
    
    def __init__(self, ip, port):
        self._server = Server((ip, port))
        
        self.game_board = chess.Board()

        ##
        ##  debug
        ##
        debug = -1
        debug_fen = ["r1bqkb1r/pppp1ppp/2n2n2/3Q4/2B1P3/8/PB3PPP/RN2K1NR w KQkq - 0 1",
                     "k7/8/8/8/2R1r3/8/8/6K1 w - - 0 1",
                     "2r5/4kppp/8/N1P5/7P/b7/5KP1/3R2N1 w - - 2 50"]
        if debug > -1:
            self.game_board = chess.Board(debug_fen[debug])

        ##import stockfish
        ##self.debug_stockfish = stockfish.Stockfish()

        self.status = STATUS_WAITING_FOR_PLAYERS

        self.game_pgn = chess.pgn.Game()
        self.game_pgn.headers["Event"] = "ChessGame.py match"
        self.game_pgn.setup(self.game_board)

        self.node = self.game_pgn
    
    def broadcast(self, buf):
        self._server.broadcast(buf)

    def change_status(self, status):
        self.status = status
        self.broadcast_status()

    def broadcast_status(self):
        print("broadcasting status:", self.status)
        self.broadcast(make_packet(PACKET_STATUS, bytes([self.status])))

    def broadcast_board(self, is_capture=0):
        data = self.game_board.epd()
        self.broadcast(make_packet(PACKET_BOARD,bytes([is_capture])+write_utf8_string(data)))

    def broadcast_client_info(self):
        for idx,client in self._server.get_clients():
            for idx2,update_client in self._server.get_clients():
                update_client.send(make_packet(PACKET_PLAYER_INFO, bytes([idx]) + write_utf8_string(client.nick)))

    def board_move(self, from_square, to_square):
        captured_piece = None ## return what was captured to client

        move = chess.Move(from_square, to_square)

        ## if pawn, rank 0 or 7, promote to queen
        print(chess.square_rank(to_square))
        ##print(self.game_board.piece_at(from_square).piece_type == chess.PAWN)
        if chess.square_rank(move.to_square) in [0, 7] and self.game_board.piece_at(move.from_square).piece_type == chess.PAWN:
            move.promotion = chess.QUEEN

        ## info for client
        if self.game_board.is_en_passant(move):
            captured_piece = chess.PAWN
        elif self.game_board.is_capture(move):
            captured_piece = self.game_board.piece_at(to_square).piece_type

        ##self.stockfish.set_fen_position(self.game_board.fen())
        
        self.game_board.push(move)
        self.broadcast_board(1 if not captured_piece is None else 0)
        ## fix for capture sound on client

        ## add to PGN
        self.node = self.node.add_variation(move)

        ## try to save
        ##print(self.game)
        white_nick = self._server.get_client(0).nick
        black_nick = self._server.get_client(1).nick
        
        self.match_name = unidecode.unidecode("{0}_{1}_{2}.pgn".format(white_nick, black_nick, self.start_time.strftime("%Y-%m-%d_%H-%M-%S")))
        
        f = open(os.path.join(MATCH_DIR, self.match_name), "w")
        f.write(str(self.game_pgn))
        f.close()

        outcome = self.game_board.outcome()
        if not outcome is None:
            ## the game has ended!
            self.change_status(STATUS_GAME_ENDED)
            self.broadcast(make_packet(PACKET_GAME_OUTCOME, bytes([outcome.termination.value, outcome.winner if not outcome.winner is None else 0])))

        return captured_piece
    
    def update(self):
        if self.status == STATUS_SERVER_STOPPED:
            return

        ## send status packet to new clients
        if len(self._server.get_new_clients()) > 0:
            self.broadcast_status()

        if self.status == STATUS_PLAYING and self._server.get_num_clients() <= 1:
            self.change_status(STATUS_GAME_ENDED_PLAYER_LEFT)

        ## enough clients
        if self.status == STATUS_WAITING_FOR_PLAYERS and self._server.get_num_clients() == 2:
            self.change_status(STATUS_PLAYING)
            self.broadcast_board()

            self._server.get_client(0).send(make_packet(PACKET_SIDE, bytes([0])))
            self._server.get_client(1).send(make_packet(PACKET_SIDE, bytes([1])))

            self.start_time = datetime.now()
            self.game_pgn.headers["Date"] = self.start_time

        for cl_idx,packets in self._server.update().items():
            cl = self._server.get_client(cl_idx)
            for packet in packets:
                pID, pDATA = packet

                ## move only if game in progress
                if pID == PACKET_MOVE and self.status == STATUS_PLAYING:
                    from_square = pDATA[0]
                    to_square = pDATA[1]

                    ## each client can only move his own pieces
                    if cl_idx == 0 and self.game_board.turn == chess.WHITE or cl_idx == 1 and self.game_board.turn == chess.BLACK:
                        print(f"ChessServer: move {from_square} {to_square}")

                        taken_piece = self.board_move(from_square, to_square)

                        ## inform other player about the move 
                        for cl2_idx,cl2 in self._server.get_clients():
                            if cl2 != cl:
                                ## the position
                                cl2.send(make_packet(PACKET_CLIENT_MOVE_INFO, bytes([from_square, to_square])))
                                ## taken piece
                                if not taken_piece is None:
                                    cl2.send(make_packet(PACKET_CLIENT_TAKEN_INFO, bytes([taken_piece])))

                if pID == PACKET_SET_NICK:
                    nick = read_utf8_string(pDATA)
                    print(f"ChessServer: client {cl_idx} set nick {nick}")

                    if cl_idx <= 1:
                    
                        self.game_pgn.headers[["White", "Black"][cl_idx]] = nick

                    cl.nick = nick

                    ## send everybody client info
                    self.broadcast_client_info()

                ## gave up
                if pID == PACKET_GIVE_UP and self.status == STATUS_PLAYING:
                    if cl_idx <= 1:
                        print(cl_idx, "gave up")
                        self.change_status(STATUS_GAME_ENDED)
                        self.broadcast(make_packet(PACKET_GAME_OUTCOME, bytes([OUTCOME_RESIGNED, 0 if cl_idx == 1 else 1])))

    ## a very sad day today
    def stop(self):
        self.status = STATUS_SERVER_STOPPED
        self._server.stop()
        
## connects to server
class ChessClient:
    def __init__(self, ip, port, nick="newbie"):
        self._client = Client.new_connection((ip, port))

        self.nick = nick

        self._client.send(make_packet(PACKET_SET_NICK, write_utf8_string(self.nick)))
    
    def update(self):
        return self._client.update()

    def disconnect(self):
        self._client.disconnect()
        
    def send_move(self, from_square, to_square):
        self._client.send(make_packet(PACKET_MOVE, bytes([from_square, to_square])))

    def give_up(self):
        self._client.send(make_packet(PACKET_GIVE_UP, b""))

class ClientBoard:
    def __init__(self, initial_board, client, side=0):
        self.board = initial_board
        self.side = side
        self.tile_size = 60

        self.board_c1 = (255, 207, 159)
        self.board_c2 = (210, 140, 69)

        self.black_player = "Black"
        self.white_player = "White"

        act_btn_w = 310
        
        self.btn_leave = GuiButton((0, 0), FONT_ACCENT.render("Leave", True, (0, 0, 0)), min_w=act_btn_w)
        self.btn_give_up = GuiButton((0, 0), FONT_ACCENT.render("Resign", True, (0, 0, 0)), min_w=act_btn_w)

        for btn in [self.btn_leave, self.btn_give_up]:
            btn.set_pos((w-btn.rect.w-5, h-btn.rect.h-5))
        self.btn_leave_show_when = [STATUS_WAITING_FOR_PLAYERS, STATUS_NOT_CONNECTED, STATUS_GAME_ENDED, STATUS_GAME_ENDED_PLAYER_LEFT]
        self.btn_give_up_show_when = [STATUS_PLAYING]

        ## render board surface
        self.board_surface = pygame.Surface((self.tile_size*8, self.tile_size*8), pygame.SRCALPHA)
        self.board_surf_white = self.board_surface.copy()
        self.board_surf_black = self.board_surface.copy()
        for y in range(0, 8):
            for x in range(0, 8):
                rect = pygame.Rect(x*self.tile_size, y*self.tile_size, self.tile_size, self.tile_size)
                clr = self.board_c2 if ((x+y)%2) else self.board_c1
                text_clr = self.board_c2 if clr == self.board_c1 else self.board_c1
                
                self.board_surface.fill(clr, rect)
                ## bottom row
                files = "ABCDEFGH"
                if y == 7 or x == 0:
                    if y == 7:
                        lbw = files[x]
                        lbb = files[7-x]
                        lb_pos = ((x+1)*self.tile_size-FONT_LABEL.get_height()+7, ((y+1)*self.tile_size)-FONT_LABEL.get_height()+3)
                        
                        self.board_surf_white.blit(FONT_LABEL.render(f"{lbw}", True, text_clr), lb_pos)
                        self.board_surf_black.blit(FONT_LABEL.render(f"{lbb}", True, text_clr), lb_pos)
                    if x == 0:
                        lbw = 7-y+1
                        lbb = y+1
                        lb_pos = ((x*self.tile_size)+2, (y*self.tile_size))
                        
                        self.board_surf_white.blit(FONT_LABEL.render(f"{lbw}", True, text_clr), lb_pos)
                        self.board_surf_black.blit(FONT_LABEL.render(f"{lbb}", True, text_clr), lb_pos)

        self.board_size = self.board_surface.get_size()
        
        self.selection_square = None
        self.move_squares = []

        self.status = STATUS_NOT_CONNECTED
        self.client = client

        self.enemy_move = None
        self.enemy_taken_piece = None
        self.outcome = None

    def server_update(self, packets):
        if packets is None:
            self.status = STATUS_NOT_CONNECTED
            return
            
        for packet in packets:
            pID, pDATA = packet

            if pID == PACKET_STATUS:
                self.status = pDATA[0]

            if pID == PACKET_SIDE:
                self.side = pDATA[0]

            if pID == PACKET_PLAYER_INFO:
                player_id = pDATA[0]
                player_name = read_utf8_string(pDATA[1:])

                print("Client: client info", player_id, player_name)

                if player_id == 0:
                    self.white_player = player_name
                if player_id == 1:
                    self.black_player = player_name

            ## board changed
            if pID == PACKET_BOARD:
                ## if we had anything selected, cancel it
                self.cancel_selection()
                is_capture = pDATA[0]

                tmp = self.board.copy()
                self.board.set_epd(read_utf8_string(pDATA[1:]))

                if tmp != self.board:
                    if is_capture != 0:
                        sound_capture.play()
                    else:
                        sound_move.play()

            ## info what the enemy moved
            if pID == PACKET_CLIENT_MOVE_INFO:
                self.enemy_move = chess.Move(pDATA[0], pDATA[1])

            if pID == PACKET_CLIENT_TAKEN_INFO:
                self.enemy_taken_piece = pDATA[0]

            if pID == PACKET_GAME_OUTCOME:
                ## dirty hack for custom outcome
                if pDATA[0] == OUTCOME_RESIGNED:
                    self.outcome = chess.Outcome(pDATA[0], chess.Color(pDATA[1]))
                    
                else:  
                    self.outcome = chess.Outcome(chess.Termination(pDATA[0]), chess.Color(pDATA[1]))
                
                sound_end.play()

    def client_move(self, from_square, to_square):
        print("Client: move", from_square, to_square)

        ## reset enemy
        self.enemy_move = None
        self.enemy_taken_piece = None

        if not self.client is None:
            self.client.send_move(from_square, to_square)

    def highlight_square(self, screen, square, color=(255, 0, 0)):
        y = math.floor(square/8)
        x = square % 8

        x,y = self.transform(x, y)

        screen.fill(color, pygame.Rect((x)*self.tile_size, (y)*self.tile_size, self.tile_size, self.tile_size).inflate(-15, -15))
    
    def transform(self, x, y):
        if self.side == 0:
            return x,7-y
        return 7-x,y

    def cancel_selection(self):
        self.move_squares = []
        self.selection_square = None

    def draw(self, screen, mouse_pos):       
        screen.blit(self.board_surface, (0, 0))

        if self.side == 0:
            screen.blit(self.board_surf_white, (0, 0))
        else:
            screen.blit(self.board_surf_black, (0, 0))

        ## highlights
        if not self.enemy_move is None:
            self.highlight_square(screen, self.enemy_move.from_square, (255, 160, 120))
            self.highlight_square(screen, self.enemy_move.to_square, (255, 160, 120) if self.enemy_taken_piece is None else (128, 128, 128))

        if self.selection_square != None:
            self.highlight_square(screen, self.selection_square, (255, 255, 0))

        for dest in self.move_squares:
            self.highlight_square(screen, dest, (0, 255, 0))

        ## count missing pieces
        bp = {"R": -2, "N": -2, "B": -2, "Q": -1, "K": -1, "P": -8, "r": -2, "n": -2, "b": -2, "q": -1, "k": -1, "p": -8}
        for y in range(0, 8):
            for x in range(0, 8):
                square = chess.square(x, y)

                ## fig
            
                fig = self.board.piece_at(square)

                x,y = self.transform(x, y)
                
                if fig:
                    screen.blit(PIECES_IMG[fig.symbol()], (x*self.tile_size, y*self.tile_size))
                    bp[fig.symbol()] += 1
                    
        ## gui info
        s = UTIL_STATUS_HUMAN_READABLE[self.status]
        status_text = FONT_ACCENT.render(f"{s}", True, (0, 0, 0))

        player = self.white_player if self.board.turn else self.black_player
        playing_text = FONT.render(f"{player}'s turn!", True, (0, 0, 0))

        screen.blit(status_text, (board_w+20, 28))

        if self.status == STATUS_PLAYING:
            screen.blit(playing_text, (board_w+20, 68))

        ## taken pieces
        taken_draw_order = ["P", "R", "B", "N", "Q"]
        taken = {}
        for k in bp:
            if bp[k] < 0:
                missing = bp[k] * -1
                ## type and how much is missing
                taken[k] = missing

        for c in [chess.WHITE, chess.BLACK]:
            draw_x = board_w
            draw_y = 390 if self.side == (c != 0) else 0
            for t in taken_draw_order:
                o = t.lower() if c == chess.BLACK else t.upper()
                if o in taken:
                    for n in range(taken[o]):
                        screen.blit(ICON_PIECES[o], (draw_x, draw_y))

                        draw_pad = ICON_PIECE_SIZE
                        ## stack pawns a bit (keep pad when changing type)
                        if (t == "P") and n < taken[o]-1:
                            draw_pad /= 2.5
                        else:
                            draw_pad /= 1.25
                        draw_x += draw_pad
                           
        if not self.enemy_taken_piece is None:
            taken_text = FONT.render(f"Piece lost:", True, (0, 0, 0))
            screen.blit(taken_text, (board_w+20, 140))

            p = PIECES_IMG[chess.Piece(self.enemy_taken_piece, self.side != 1).symbol()]
            takenx,takeny = center_horiz((w-board_w, h), p.get_size(), 180)

            screen.blit(p, (takenx+board_w, takeny))

        if not self.outcome is None:
            player = self.white_player if self.outcome.winner else self.black_player

            t_name = "Terminated"
            t_winner = "Draw"

            if self.outcome.termination == chess.Termination.CHECKMATE:
                t_name = "Checkmate"
                t_winner = f"{player} won!" + (" (you)" if (self.outcome.winner == (self.side == 0)) else "")
            if self.outcome.termination == chess.Termination.STALEMATE:
                t_name = "Stalemate"
            if self.outcome.termination == chess.Termination.INSUFFICIENT_MATERIAL:
                t_name = "Insufficient material"
            if self.outcome.termination == chess.Termination.FIVEFOLD_REPETITION:
                t_name = "Fivefold repetition"
            if self.outcome.termination == OUTCOME_RESIGNED:
                t_winner = f"{player} resigned!" + (" (you)" if (self.outcome.winner == (self.side == 0)) else "")

            outcome_text = FONT_ACCENT.render(t_name, True, (0, 0, 0))
            outcome_text_winner = FONT.render(t_winner, True, (0, 0, 0))

            screen.blit(outcome_text, (board_w+20, 300))
            screen.blit(outcome_text_winner, (board_w+20, 340))

        if self.status in self.btn_leave_show_when:
            self.btn_leave.draw(screen)

        if self.status in self.btn_give_up_show_when and mouse_pos[0] >= board_w and mouse_pos[1] >= h-75:
            self.btn_give_up.draw(screen)

    def update(self, events, mouse_pos):
        if self.status in self.btn_leave_show_when:
            self.btn_leave.update(events, mouse_pos)

        if self.status in self.btn_give_up_show_when and mouse_pos[0] >= board_w and mouse_pos[1] >= h-75:
            self.btn_give_up.update(events, mouse_pos)

        if self.btn_give_up.pressed:
            self.client.give_up()
            self.btn_give_up.update(events, mouse_pos)
            
        if self.btn_leave.pressed:
            return False
        
        for e in events:
            ## right click: cancel selection
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == pygame.BUTTON_RIGHT:
                self.cancel_selection()
                
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == pygame.BUTTON_LEFT:
                x,y = e.pos

                ## game not running or not clicked in board
                if self.status != STATUS_PLAYING or x > board_w or y > board_w:
                    ## just cancel selection
                    self.cancel_selection()
                    continue

                tx = math.floor(x/self.tile_size)
                ty = math.floor(y/self.tile_size)

                tx,ty = self.transform(tx, ty)

                square = chess.square(tx, ty)

                ## chose a move
                if len(self.move_squares) != 0:
                    if square in self.move_squares:
                        self.client_move(self.selection_square, square)

                        ## unselect
                        self.move_squares = []
                        self.selection_square = None
                        return
                        
                ## chose a piece
                if self.board.piece_at(square) != None:
                    self.move_squares = []

                    ## deny selection if it isn't your piece
                    if not self.board.color_at(square) == self.side:

                        ## find valid moves
                        self.selection_square = square
                        for m in self.board.legal_moves:
                            if m.from_square == square:
                                self.move_squares.append(m.to_square)

                        ## deny selection if no valid moves
                        if len(self.move_squares) == 0:
                            self.selection_square = None
                ## chose nothing
                else:
                    self.move_squares = []
                    
                    self.selection_square = None

def transform(pos, pos2):
    return (pos[0]+pos2[0], pos[1]+pos2[1])
                
def center(container_size, size):
    return ((container_size[0]-size[0])/2, (container_size[1]-size[1])/2)

def center_horiz(container_size, size, h):
    return (center(container_size, size)[0], h)

def below_title():
    return GUI_PAD * 2 + FONT_TITLE.get_height()

CONFIG_FILE = "config.json"

def get_json_content(file):
    if os.path.exists(file):
        return json.loads(open(file, encoding="utf-8").read())
    else:
        return None

def save_config(data):
    d = json.dumps(data)

    f = open(CONFIG_FILE, "w")
    f.write(d)
    f.close()

def get_client_config():
    config = get_json_content(CONFIG_FILE)

    if not config:
        save_config({})

    return get_json_content(CONFIG_FILE)

def client_preset_load(idx):
    idx = str(idx)
    
    c = get_client_config()

    if "presets" in c:
        presets = c["presets"]
        if idx in presets:
            preset = presets[idx]
            if "ip" in preset and "nick" in preset:
                return preset["ip"], preset["nick"]

    return None

def client_preset_save(idx, ip, username):
    idx = str(idx)
    preset = {"ip": ip, "nick": username}

    c = get_client_config()
    if not "presets" in c:
        c["presets"] = {}
    print(c["presets"])
    c["presets"][idx] = preset
    save_config(c)

pygame.mixer.init(44100, -16, 1, 1024)
pygame.init()
pygame.key.set_repeat(500, 25)
pygame.display.set_caption("Chess")

clock = pygame.time.Clock()

ASSETS_DIR = "./assets/"
MATCH_DIR = "./matches/"
IMG_DIR = os.path.join(ASSETS_DIR, "pieces")
ICONS_DIR = os.path.join(ASSETS_DIR, "gui")
SOUND_DIR = os.path.join(ASSETS_DIR, "sound")

def load_sound(name):
    return pygame.mixer.Sound(os.path.join(SOUND_DIR, f"{name}.wav"))

about_sounds = []
for i in range(1, 9):
    about_sounds.append(load_sound(f"tone{i:02d}"))

sound_error = load_sound("error")
sound_move = load_sound("move")
sound_capture = load_sound("capture")
sound_end = load_sound("end")

if not os.path.exists(MATCH_DIR):
    os.mkdir(MATCH_DIR)

BASE_PIECES_NUM = {"R": 2,
                     "N": 2,
                     "B": 2,
                     "Q": 1,
                     "K": 1,
                     "P": 8,
                     "r": 2,
                     "n": 2,
                     "b": 2,
                     "q": 1,
                     "k": 1,
                     "p": 8} 

PIECES_FILENAME = {"R": "Vb",
                   "N": "Jb",
                   "B": "Sb",
                   "Q": "Db",
                   "K": "Kb",
                   "P": "Pb",
                   "r": "Vc",
                   "n": "Jc",
                   "b": "Sc",
                   "q": "Dc",
                   "k": "Kc",
                   "p": "Pc"}

ICON_PIECE_SIZE = 30
PIECES_IMG = {}
ICON_PIECES = {}
for item in PIECES_FILENAME:
    surf = pygame.image.load(os.path.join(IMG_DIR, PIECES_FILENAME[item] + ".png"))
    PIECES_IMG[item] = surf
    ICON_PIECES[item] = pygame.transform.rotozoom(surf, 0, ICON_PIECE_SIZE/surf.get_size()[0])##pygame.transform.smoothscale(surf, (ICON_PIECE_SIZE, ICON_PIECE_SIZE))

bg_image = pygame.image.load(os.path.join(ICONS_DIR, "background02.png"))
PIECES_I = list(PIECES_IMG.items())

FONT = pygame.font.Font(os.path.join(ASSETS_DIR, "OpenSans-Regular.ttf"), 28)
FONT_LABEL = pygame.font.Font(os.path.join(ASSETS_DIR, "OpenSans-ExtraBold.ttf"), 14)
FONT_ACCENT = pygame.font.Font(os.path.join(ASSETS_DIR, "OpenSans-SemiBold.ttf"), 28)
FONT_SMALL_ACCENT = pygame.font.Font(os.path.join(ASSETS_DIR, "OpenSans-SemiBold.ttf"), 22)
FONT_TITLE = pygame.font.Font(os.path.join(ASSETS_DIR, "OpenSans-ExtraBold.ttf"), 48)

presets = ["save01.png", "load01.png", "save02.png", "load02.png"]
preset_icons = []

for p in presets:
    preset_icon = pygame.image.load(os.path.join(ICONS_DIR, p))
    preset_icons.append(preset_icon)

GAME_ICON = pygame.image.load(os.path.join(ICONS_DIR, "icon.png"))

STATE_MENU = 0
STATE_ABOUT = 1
STATE_JOIN = 2
STATE_CREATE = 3
STATE_PLAYING = 4
STATE_END = 5
GAME_STATE = 0

STATE_TITLES = ["Chess Game", "About", "Join Server", "Create Server"]

about_url = "https://www.markop1.cz"
about_text_string = ["ChessGame.py", "Coded in 2023 by Markop1CZ", "", "Uses the pygame and chess library", "", about_url]
about_text = []
link_rect = pygame.Rect(0, 0, 0, 0)
for i,txt in enumerate(about_text_string):
    if i == 0:
        fnt = FONT_TITLE
    else:
        fnt = FONT_ACCENT

    if txt == about_url:
        about_url_i = i
        fnt.underline = True

    about_text.append(fnt.render(txt, True, (255, 255, 255)))
    fnt.underline = False

T_SIZE = 60
board_w = T_SIZE*8
w = board_w + 320
h = T_SIZE*8

GUI_PAD = 20
GUI_MENU_BTN_PAD = 25

## buttons for MENU

menu_btn_w = 350
menu_btn_x = (w-menu_btn_w)/2

place_y = below_title()

btn_join = GuiButton((menu_btn_x, place_y), FONT_ACCENT.render("Join server", True, (0, 0, 0)), min_w=menu_btn_w)
place_y += GUI_PAD + btn_join.rect.h
btn_create = GuiButton((menu_btn_x, place_y), FONT_ACCENT.render("Create server", True, (0, 0, 0)), min_w=menu_btn_w)
place_y += GUI_PAD + btn_join.rect.h
btn_about = GuiButton((menu_btn_x, place_y), FONT_ACCENT.render("About", True, (0, 0, 0)), min_w=menu_btn_w)
place_y += GUI_PAD + btn_join.rect.h
btn_quit = GuiButton((menu_btn_x, place_y), FONT_ACCENT.render("Quit", True, (0, 0, 0)), min_w=menu_btn_w)

menu_btns = [btn_join, btn_create, btn_about, btn_quit]

## buttons for CREATE

menu_entry_w = 500
entry_x = (w-menu_entry_w)/2
place_y = below_title()

entry_ip = GuiEntry((entry_x, place_y), FONT_ACCENT, initial_text="127.0.0.1", min_w=menu_entry_w, max_length=30, _type=ENTRY_TYPE_TEXT)
place_y += GUI_PAD + entry_ip.h
entry_name = GuiEntry((entry_x, place_y), FONT_ACCENT, initial_text="newbie", min_w=menu_entry_w, max_length=25, _type=ENTRY_TYPE_TEXT)
place_y += GUI_PAD + entry_name.h

## only hack for different text
btn_entry_create = GuiButton((entry_x, place_y), FONT_ACCENT.render("Host", True, (0, 0, 0)), min_w=menu_entry_w)
btn_entry_join = GuiButton((entry_x, place_y), FONT_ACCENT.render("Connect", True, (0, 0, 0)), min_w=menu_entry_w)
btn_entry_back = GuiButton((GUI_BTN_PAD, GUI_BTN_PAD), FONT_ACCENT.render("Back", True, (0, 0, 0)), min_w=120)

entry_err_txt = None
entry_preset_buttons = []
entry_preset_btn_size = 55

tmp = btn = GuiButton((0, 0), preset_icons[0], min_w=entry_preset_btn_size)

place_x = w - tmp.rect.w - GUI_BTN_PAD
place_y = h - tmp.rect.h - GUI_BTN_PAD
for icn in preset_icons[::-1]:
    btn = GuiButton((place_x, place_y), icn, min_w=entry_preset_btn_size)
    entry_preset_buttons.append(btn)

    place_x -= GUI_BTN_PAD + btn.rect.w

## buttons for JOIN
join_entry = [entry_ip, entry_name]
menu_entry_focus = EntryFocusManager([entry_ip, entry_name])

menu_copyright = FONT_SMALL_ACCENT.render("Copyright © 2023 Markop1CZ", True, (0, 0, 0))

pygame.display.set_icon(GAME_ICON)

white = (255, 255, 255)
screen = pygame.display.set_mode((w, h))

board = ClientBoard(chess.Board(), None, side=0)

GAME_SERVER = None
GAME_CLIENT = None
GAME_RUNNING = True
while GAME_RUNNING:
    events = pygame.event.get()
    mouse = pygame.mouse.get_pos()
    screen.fill(white)

    if GAME_STATE < STATE_PLAYING:
        title = FONT_TITLE.render(STATE_TITLES[GAME_STATE], True, (0, 0, 0))
        if GAME_STATE == STATE_MENU:
            screen.blit(bg_image, (0, 0))
        screen.blit(title, center_horiz((w, h), title.get_size(), GUI_PAD))

        ## MENU
        if GAME_STATE == STATE_MENU:
            for btn in menu_btns:
                btn.update(events, mouse)
                btn.draw(screen)

            screen.blit(menu_copyright, (2, h-menu_copyright.get_size()[1]))

            if btn_join.pressed:
                GAME_STATE = STATE_JOIN
                entry_err_txt = None
            if btn_create.pressed:
                GAME_STATE = STATE_CREATE
                entry_err_txt = None
            if btn_about.pressed:
                GAME_STATE = STATE_ABOUT
                about_background = pygame.Surface((w, h))
                about_background.fill(white)
                about_i = 0
            if btn_quit.pressed:
                GAME_STATE = STATE_END
                GAME_RUNNING = False

        ## JOIN or CREATE
        if GAME_STATE in [STATE_JOIN, STATE_CREATE]:
            menu_entry_focus.update(events, mouse)
            for entry in join_entry:
                entry.draw(screen)

            for i,btn in enumerate(entry_preset_buttons[::-1]):
                btn.draw(screen)
                btn.update(events, mouse)

                if btn.pressed:
                    ## save
                    if i%2 == 0:
                        idx = int((i/2))
                        
                        client_preset_save(idx, entry_ip.get(), entry_name.get())
                        entry_err_txt = FONT_ACCENT.render("Preset: Preset {0} saved.".format(idx+1), True, (0, 0, 0))
                    ## load
                    else:
                        idx = int(((i-1)/2))

                        l = client_preset_load(idx)
                        if not l is None:
                            ip,nick = l
                            entry_ip.set_input(ip)
                            entry_name.set_input(nick)

                            entry_err_txt = FONT_ACCENT.render("Preset: Preset {0} loaded.".format(idx+1), True, (0, 0, 0))
                        else:
                            entry_err_txt = FONT_ACCENT.render("Preset: No preset {0}.".format(idx+1), True, (0, 0, 0))

            if GAME_STATE == STATE_JOIN:
                btn = btn_entry_join
            if GAME_STATE == STATE_CREATE:
                btn = btn_entry_create

            btn_entry_back.update(events, mouse)
            btn_entry_back.draw(screen)
            if btn_entry_back.pressed:
                GAME_STATE = STATE_MENU

            if not entry_err_txt is None:
                screen.blit(entry_err_txt, center_horiz((w, h), entry_err_txt.get_size(), btn_entry_join.pos[1] + btn_entry_join.rect.h + GUI_PAD))

            btn.update(events, mouse)
            if btn.pressed:
                GAME_SERVER = None
                GAME_CLIENT = None

                ## parse input
                ip = entry_ip.get()
                port = 1337
                if ":" in ip:
                    ip,port = ip.split(":")[0:2]
                    port = int(port)

                nick = entry_name.get()

                err_string = None
                try:
                    if GAME_STATE == STATE_CREATE:
                        GAME_SERVER = ChessServer(ip, port)
                    GAME_CLIENT = ChessClient(ip, port, nick=nick)

                    board = ClientBoard(chess.Board(), GAME_CLIENT)

                    GAME_STATE = STATE_PLAYING
                ## connection errors
                except ConnectionRefusedError:
                    err_string = "Error: Connection refused!"
                except OSError as e:
                    print(e)
                    ## fuck errno.h
                    ## !!!!!
                    known_winerrors = {11001: "Error: Invalid address!",
                                       10048: "Error: Address already in use.",
                                       10049: "Error: Cannot bind/connect to this address.",
                                       10060: "Error: Timed out."}

                    if e.errno in known_winerrors:
                        err_string = known_winerrors[e.errno]
                    else:
                        err_string = "Invalid error :("
                except socket.timeout:
                    err_string = "Error: Timed out!"
                except socket.gaierror:
                    err_string = "Error: Invalid address!"

                if not err_string is None:
                    sound_error.play()
                    entry_err_txt = FONT_ACCENT.render(err_string, True, (0, 0, 0))
            btn.draw(screen)
                
    if GAME_STATE == STATE_PLAYING:
        if not GAME_SERVER is None:
            GAME_SERVER.update()
        packets = GAME_CLIENT.update()
        board.server_update(packets)
        
        board.draw(screen, mouse)

        ## user left
        if board.update(events, mouse) == False:
            GAME_STATE = STATE_MENU

            ## destroy server
            if not GAME_SERVER is None:
                GAME_SERVER.stop()

    if GAME_STATE == STATE_ABOUT:
        screen.blit(about_background, (0, 0))
        
        btn_entry_back.update(events, mouse)
        btn_entry_back.draw(screen)
        if btn_entry_back.pressed:
            GAME_STATE = STATE_MENU

        y = below_title()
        for i,txt in enumerate(about_text):
            s = txt.get_size()
            px, py = center_horiz((w, h), s, y)
            if not s[0] < 10:
                screen.fill((0, 0, 0), pygame.Rect(px, py, *s).inflate(20, 5))
            screen.blit(txt, (px, py))
            y += s[1]

            if i == about_url_i:
                link_rect = pygame.Rect(px, py, *txt.get_size())
                
        ## link highlight
        if link_rect.collidepoint(*mouse):
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
        
        ## link click
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == pygame.BUTTON_LEFT:
                if link_rect.collidepoint(e.pos):
                    webbrowser.open(about_url)
                    
        ## about background
        if about_i%18 == 0:
            about_background.blit(random.choice(PIECES_I)[1], (random.randint(-30, w-30), random.randint(-30, h-30)))
            s = random.choice(about_sounds)
            c = pygame.mixer.find_channel()
            if not c is None:
                c.play(s)
        if about_i >= 2000:
            about_background.fill(white)
            about_i = 0
        about_i += 1
            
    pygame.display.flip()
    for event in events:
        if event.type == pygame.QUIT:
            GAME_RUNNING = False
            pygame.quit()

    clock.tick(60)

if not GAME_CLIENT is None:
    GAME_CLIENT.disconnect()

if not GAME_SERVER is None:
    GAME_SERVER.stop()

pygame.display.quit()
pygame.quit()
