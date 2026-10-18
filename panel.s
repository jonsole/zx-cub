; Cub's panel on the Z80: panel.py's, the same bytes on the screen. The
; unchanging parts -- labels, the stall light's word, the bars' feet --
; are drawn once by panel_still; then each frame panel_frame works out
; what the panel shows (panel.values), and redraws only the parts that
; differ from the state's shown_ fields, on both screens at once, so that
; the panel is the same whichever is shown (docs/adr/0003).

PANEL_NUMBERS		EQU		$1080					; NUMBER_ROW's top line, from the screen's start
PANEL_BARS			EQU		$10C0					; BAR_ROW's
PANEL_LIGHT			EQU		6144 + 32 * PANEL_NUMBER_ROW + PANEL_STALL_COLUMN	; its attributes
					ASSERT	PANEL_NUMBER_ROW == 20 && PANEL_BAR_ROW == 22
					ASSERT	low PANEL_NUMBERS + PANEL_HEADING_COLUMN + PANEL_HEADING_PLACES <= 256
					ASSERT	low PANEL_BARS + PANEL_CLIMB_COLUMN + PANEL_BAR_WIDTH / 8 <= 256
					ASSERT	PANEL_HEIGHT_PLACES <= 5 && PANEL_K_MPH < $8000	; put_number's five; mul's signed 16

; The byte A at the offset DE into both screens. Uses HL.
					MACRO	BOTH_SCREENS
					ld		hl,$4000
					add		hl,de
					ld		(hl),a
					ld		hl,$C000
					add		hl,de
					ld		(hl),a
					ENDM

; panel_still: the panel's unchanging parts, on both screens. Uses AF, BC,
; DE, HL, IX.
panel_still:
					ld		bc,PANEL_STILL_COUNT
					ld		ix,panel_still_bytes
.byte:
					ld		e,(ix + 0)
					ld		d,(ix + 1)
					ld		a,(ix + 2)
					BOTH_SCREENS
					inc		ix
					inc		ix
					inc		ix
					dec		bc
					ld		a,b
					or		c
					jr		nz,.byte
					ret

; ---------------------------------------------------------------------------
; panel_frame: what the panel shows of the state (panel.values), each part
; redrawn on both screens if it differs from its shown_ field, which then
; holds it; panel_redrawn says which were (panel.REDRAWN's bits). Uses
; everything but IY and the alternate registers.
panel_frame:
					xor		a
					ld		(panel_redrawn),a

					ld		hl,(state + STATE_SPEED)	; the airspeed: ((speed >> 4) K_MPH) >> 20
					ld		a,(state + STATE_SPEED + 2)
					REPT	4
					srl		a
					rr		h
					rr		l
					EDUP
					ld		c,0
					ld		de,PANEL_K_MPH
					call	mul
					SHIFTED	20
					ld		a,(state + STATE_SHOWN_MPH)
					cp		l
					jr		z,.mph_done
					ld		a,l
					ld		(state + STATE_SHOWN_MPH),a
					ld		h,0
					ld		c,PANEL_SPEED_COLUMN
					ld		b,PANEL_SPEED_PLACES
					ld		a,PANEL_SPEED_ZEROS
					call	put_number
					ld		a,PANEL_REDRAWN_MPH
					call	redrawn
.mph_done:
					ld		hl,(state + STATE_Y + 2)	; the height: y >> 16
					ld		de,(state + STATE_SHOWN_FEET)
					or		a
					sbc		hl,de
					jr		z,.feet_done
					add		hl,de
					ld		(state + STATE_SHOWN_FEET),hl
					ld		c,PANEL_HEIGHT_COLUMN
					ld		b,PANEL_HEIGHT_PLACES
					ld		a,PANEL_HEIGHT_ZEROS
					call	put_number
					ld		a,PANEL_REDRAWN_FEET
					call	redrawn
.feet_done:
					ld		hl,(state + STATE_HEADING)	; the heading: (heading 360) >> 16
					ld		c,0
					ld		de,360
					call	mul
					SHIFTED	16
					ld		de,(state + STATE_SHOWN_HEADING)
					or		a
					sbc		hl,de
					jr		z,.heading_done
					add		hl,de
					ld		(state + STATE_SHOWN_HEADING),hl
					ld		c,PANEL_HEADING_COLUMN
					ld		b,PANEL_HEADING_PLACES
					ld		a,PANEL_HEADING_ZEROS
					call	put_number
					ld		a,PANEL_REDRAWN_HEADING
					call	redrawn
.heading_done:
					ld		a,(state + STATE_THROTTLE)	; the throttle: throttle >> THROTTLE_SHIFT
					REPT	PANEL_THROTTLE_SHIFT
					srl		a
					EDUP
					ld		hl,state + STATE_SHOWN_THROTTLE
					cp		(hl)
					jr		z,.throttle_done
					ld		(hl),a
					ld		e,a						; its pixels, from the bar's left
					ld		d,0
					ld		c,PANEL_THROTTLE_COLUMN
					call	put_bar
					ld		a,PANEL_REDRAWN_THROTTLE
					call	redrawn
.throttle_done:
					call	climb_bar_length		; the climb
					ld		hl,state + STATE_SHOWN_CLIMB
					cp		(hl)
					jr		z,.climb_done
					ld		(hl),a
					ld		d,PANEL_BAR_WIDTH / 2	; from the middle, right climbing
					ld		e,d						; and left sinking
					or		a
					jp		m,.sinking
					add		a,e
					ld		e,a
					jr		.climb_bar
.sinking:
					add		a,d
					ld		d,a
.climb_bar:
					ld		c,PANEL_CLIMB_COLUMN
					call	put_bar
					ld		a,PANEL_REDRAWN_CLIMB
					call	redrawn
.climb_done:
					call	stall_light				; the stall light
					ld		hl,state + STATE_SHOWN_STALL
					cp		(hl)
					ret		z
					ld		(hl),a
					or		a
					ld		a,PANEL_LIGHT_OFF
					jr		z,.colour
					ld		a,PANEL_LIGHT_ON
.colour:
					ld		de,PANEL_LIGHT
					ld		b,PANEL_STALL_CELLS
.cell:
					push	bc
					BOTH_SCREENS
					pop		bc
					inc		de
					djnz	.cell
					ld		a,PANEL_REDRAWN_STALL	; and on into redrawn

; panel_redrawn |= A. Uses AF, HL.
redrawn:
					ld		hl,panel_redrawn
					or		(hl)
					ld		(hl),a
					ret

; climb_bar_length: A = the climb bar's pixels, signed (panel.values): the
; rise ((speed >> 3) sin16(gamma >> 8)) >> 12, then (|rise| K_CLIMB) >> 16,
; held to CLIMB_REACH, the rise's sign. Uses AF, BC, DE, HL.
climb_bar_length:
					ld		hl,(state + STATE_SPEED)
					ld		a,(state + STATE_SPEED + 2)
					REPT	3
					srl		a
					rr		h
					rr		l
					EDUP
					push	hl
					ld		hl,(state + STATE_GAMMA + 1)
					call	sin16
					pop		hl
					ld		c,0
					call	mul
					SHIFTED	12
					ld		a,d						; the rise's sign
					ld		(.sign),a
					bit		7,d						; |rise|, 24 bits
					jr		z,.size
					xor		a
					sub		l
					ld		l,a
					ld		a,0
					sbc		a,h
					ld		h,a
					ld		a,0
					sbc		a,e
					ld		e,a
.size:
					ld		c,e
					ld		de,PANEL_K_CLIMB
					call	mul
					SHIFTED	16
					ld		a,h						; held to CLIMB_REACH
					or		a
					jr		nz,.most
					ld		a,l
					cp		PANEL_CLIMB_REACH + 1
					jr		c,.held
.most:
					ld		a,PANEL_CLIMB_REACH
.held:
					ld		b,a
					ld		a,(.sign)
					or		a
					ld		a,b
					ret		p
					neg
					ret
.sign:				DB		0

; stall_light: A = 1 if the stall light is lit (flight.stall_warning): in
; the air, stalled or the wing's attack at least ALPHA_WARNING. Uses AF,
; DE, HL.
stall_light:
					ld		a,(state + STATE_FLAGS)
					ld		e,a
					xor		a
					bit		1,e						; GROUND: unlit
					ASSERT	GROUND == 2 && STALLED == 4
					ret		nz
					inc		a
					bit		2,e						; STALLED: lit
					ret		nz
					ld		de,(state + STATE_GAMMA + 1)	; attack = pitch - (gamma >> 8)
					ld		hl,(state + STATE_PITCH)	; + INCIDENCE
					or		a
					sbc		hl,de
					ld		de,INCIDENCE
					add		hl,de
					ld		de,ALPHA_WARNING
					call	compare					; carry: under the warning
					ld		a,0
					ret		c
					inc		a
					ret

; put_number: HL as panel.digits writes it, B places from column C of
; NUMBER_ROW, led by zeros if A is non-zero, else by blanks (the last digit
; always a digit). Uses everything but IY and the alternate registers.
put_number:
					ld		(.zeros),a
					push	bc
					ld		ix,.digits				; five decimal digits, the most
					ld		de,10000				; significant first
					call	.digit
					ld		de,1000
					call	.digit
					ld		de,100
					call	.digit
					ld		de,10
					call	.digit
					ld		(ix + 0),l
					pop		bc
					ld		a,5						; the last B of them
					sub		b
					ld		e,a
					ld		d,0
					ld		ix,.digits
					add		ix,de
					ld		a,(.zeros)
					ld		(.leading),a			; non-zero: draw zeros as zeros
.place:
					ld		a,(ix + 0)
					or		a
					jr		nz,.figure
					ld		a,(.leading)
					or		a
					jr		nz,.figure
					ld		a,b						; the last place is always a
					dec		a						; digit
					jr		z,.figure
					ld		a,PANEL_BLANK
					jr		.put
.figure:
					ld		a,1
					ld		(.leading),a
					ld		a,(ix + 0)
.put:
					push	bc
					push	ix
					call	put_glyph
					pop		ix
					pop		bc
					inc		c
					inc		ix
					djnz	.place
					ret
.digit:
					xor		a						; (ix) = HL / DE, HL = what is left
.subtract:
					or		a
					sbc		hl,de
					jr		c,.digit_done
					inc		a
					jr		.subtract
.digit_done:
					add		hl,de
					ld		(ix + 0),a
					inc		ix
					ret
.digits:			DS		5
.zeros:				DB		0
.leading:			DB		0

; put_glyph: digit_glyphs' glyph A (0 to 9, 10 a blank) in column C of
; NUMBER_ROW, on both screens. Uses AF, B, DE, HL, IX.
put_glyph:
					add		a,a
					add		a,a
					add		a,a
					ld		e,a
					ld		d,0
					ld		ix,digit_glyphs
					add		ix,de
					ld		e,c
					ld		d,high PANEL_NUMBERS
					ld		a,e
					add		a,low PANEL_NUMBERS
					ld		e,a
					ld		b,8
.line:
					ld		a,(ix + 0)
					BOTH_SCREENS
					inc		ix
					inc		d						; the next pixel line, 256 on
					djnz	.line
					ret

; put_bar: a bar's eight bytes from column C of BAR_ROW, inked from pixel D
; to pixel E - 1 of its BAR_WIDTH, on each of its BAR_LINES, on both screens.
; Uses everything but IY and the alternate registers.
put_bar:
					ld		ix,.bytes
					ASSERT	PANEL_BAR_WIDTH == 64
					ld		b,PANEL_BAR_WIDTH / 8	; each byte: the pixels from D to
.byte:												; E that fall in it, as
					ld		a,e						; left_masks[E] and not
					call	.within					; left_masks[D], each held to
					push	de						; the byte's 0 to 8
					ld		e,a
					ld		d,0
					ld		hl,left_masks
					add		hl,de
					ld		a,(hl)
					pop		de
					push	af
					ld		a,d
					call	.within
					push	de
					ld		e,a
					ld		d,0
					ld		hl,left_masks
					add		hl,de
					pop		de
					pop		af
					xor		(hl)					; the D side's bits are within the
					ld		(ix + 0),a				; E side's, or none of them
					inc		ix
					ld		a,d						; the next byte: 8 pixels on
					sub		8
					ld		d,a
					ld		a,e
					sub		8
					ld		e,a
					djnz	.byte
					ld		a,c						; the bar's lines
					add		a,low (PANEL_BARS + 256 * PANEL_BAR_FIRST_LINE)
					ld		e,a
					ld		d,high (PANEL_BARS + 256 * PANEL_BAR_FIRST_LINE)
					ld		c,PANEL_BAR_LINES
.line:
					ld		ix,.bytes
					ld		b,8
					push	de
.put:
					ld		a,(ix + 0)
					push	bc
					BOTH_SCREENS
					pop		bc
					inc		ix
					inc		e
					djnz	.put
					pop		de
					inc		d
					dec		c
					jr		nz,.line
					ret
; A held to 0..8, signed. Uses AF.
.within:
					or		a
					jp		p,.positive
					xor		a
					ret
.positive:
					cp		9
					ret		c
					ld		a,8
					ret
.bytes:				DS		8

; left_masks[k]: the leftmost k pixels of a byte.
left_masks:			DB		$00, $80, $C0, $E0, $F0, $F8, $FC, $FE, $FF

panel_redrawn:		DB		0						; panel.REDRAWN's bits, this frame
digit_glyphs:		DIGIT_GLYPHS
panel_still_bytes:	PANEL_STILL
