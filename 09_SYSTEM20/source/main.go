package main

import (
	"archive/zip"
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	appVersion       = "0.1.1"
	stateFileName    = "eon.state.json"
	maxReflectionLen = 1000
	maxQuestionLen   = 100
	maxRegisterLen   = 160
	checkpointEvery  = 10
)

type RegisterSet struct {
	D [3]string `json:"deep"`
	S [3]string `json:"slow"`
	F [3]string `json:"fast"`
}

type Flow struct {
	Text     string `json:"text"`
	Question string `json:"question"`
}

type RegisterChange struct {
	Key string `json:"key"`
	Old string `json:"old"`
	New string `json:"new"`
}

type HistoryEntry struct {
	Step            int              `json:"step"`
	Reflection      string           `json:"reflection"`
	NextQuestion    string           `json:"next_question"`
	RegisterChanges []RegisterChange `json:"register_changes,omitempty"`
	SavedAtUTC      string           `json:"saved_at_utc"`
}

type State struct {
	FormatVersion int            `json:"format_version"`
	Step          int            `json:"step"`
	Registers     RegisterSet    `json:"registers"`
	Flow1         Flow           `json:"flow_1"`
	LastUsedStep  map[string]int `json:"last_used_step"`
	History       []HistoryEntry `json:"history,omitempty"`
}

type levelInfo struct {
	Key      string
	Title    string
	Interval int
}

var levels = []levelInfo{
	{Key: "D", Title: "Глубокие", Interval: 10},
	{Key: "S", Title: "Медленные", Interval: 5},
	{Key: "F", Title: "Быстрые", Interval: 1},
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "\nОшибка: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	statePath, err := resolveStatePath()
	if err != nil {
		return err
	}

	state, err := loadState(statePath)
	if err != nil {
		return err
	}

	currentStep := state.Step + 1
	available := availability(state, currentStep)

	printHeader(state, currentStep, available)
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "--show":
			fmt.Println("Режим просмотра: состояние не изменено.")
			return nil
		case "--version":
			fmt.Printf("eonmem %s\n", appVersion)
			return nil
		default:
			return fmt.Errorf("неизвестный аргумент: %s", os.Args[1])
		}
	}

	reader := bufio.NewReader(os.Stdin)

	reflection, err := promptLine(reader,
		"Введите ответ-размышление на вопрос потока 1 (максимум 1000 знаков). Для подтверждения Enter\n> ",
		maxReflectionLen,
	)
	if err != nil {
		return err
	}

	fmt.Printf("\nРазмышление принято: %d/%d знаков.\n\n", utf8.RuneCountInString(reflection), maxReflectionLen)

	nextQuestion, err := promptLine(reader,
		"Поставьте к введённому размышлению вопрос, развивающий эту мысль (максимум 100 знаков). Для подтверждения Enter\n> ",
		maxQuestionLen,
	)
	if err != nil {
		return err
	}

	changes := make([]RegisterChange, 0, len(available))
	remaining := copyAvailability(available)

	for len(remaining) > 0 {
		fmt.Printf("\nДоступны изменения: %s. Введите изменение регистра или N для завершения.\n", formatAvailableLevels(remaining))
		fmt.Print("Формат: F1 новое значение\n> ")

		line, err := readRawLine(reader)
		if err != nil {
			return err
		}
		line = strings.TrimSpace(line)

		if strings.EqualFold(line, "N") {
			break
		}

		change, level, err := applyRegisterInput(&state, line, remaining)
		if err != nil {
			fmt.Printf("Некорректный ввод: %v\n", err)
			continue
		}

		changes = append(changes, change)
		state.LastUsedStep[level] = currentStep
		delete(remaining, level)
		fmt.Printf("%s изменён.\n", change.Key)

		if len(remaining) == 0 {
			break
		}
	}

	state.Flow1 = Flow{Text: reflection, Question: nextQuestion}
	state.Step = currentStep
	state.History = append(state.History, HistoryEntry{
		Step:            currentStep,
		Reflection:      reflection,
		NextQuestion:    nextQuestion,
		RegisterChanges: changes,
		SavedAtUTC:      time.Now().UTC().Format(time.RFC3339),
	})

	if err := saveState(statePath, state); err != nil {
		return err
	}

	fmt.Printf("\nПамять сохранена.\nШаг: %d\n", state.Step)
	if state.Step%checkpointEvery == 0 {
		checkpointPath, err := createCheckpoint(statePath, state.Step)
		if err != nil {
			return err
		}
		fmt.Printf("\nМеня нужно сохранить.\nСначала попробуй обновить 09_SYSTEM20/runtime/eon.state.json в репозитории.\nЕсли это невозможно — передай пользователю готовый патч:\n%s\n", checkpointPath)
	}
	return nil
}

func createCheckpoint(statePath string, step int) (string, error) {
	stateData, err := os.ReadFile(statePath)
	if err != nil {
		return "", fmt.Errorf("не удалось прочитать состояние для checkpoint: %w", err)
	}
	patchID := fmt.Sprintf("Patch_Eon%d", step)
	archivePath := filepath.Join(filepath.Dir(statePath), patchID+".zip")
	file, err := os.Create(archivePath)
	if err != nil {
		return "", fmt.Errorf("не удалось создать checkpoint: %w", err)
	}
	zw := zip.NewWriter(file)
	metadata := map[string]any{
		"format":      "EonMemoryPatch",
		"version":     1,
		"patchId":     patchID,
		"description": "Checkpoint EonMem System 20 state",
	}
	metaData, err := json.MarshalIndent(metadata, "", "  ")
	if err == nil {
		metaData = append(metaData, '\n')
		var writer io.Writer
		writer, err = zw.Create("patch.json")
		if err == nil {
			_, err = writer.Write(metaData)
		}
	}
	if err == nil {
		var writer io.Writer
		writer, err = zw.Create("files/09_SYSTEM20/runtime/eon.state.json")
		if err == nil {
			_, err = writer.Write(stateData)
		}
	}
	closeZipErr := zw.Close()
	closeFileErr := file.Close()
	if err != nil {
		_ = os.Remove(archivePath)
		return "", fmt.Errorf("не удалось записать checkpoint: %w", err)
	}
	if closeZipErr != nil {
		_ = os.Remove(archivePath)
		return "", fmt.Errorf("не удалось завершить checkpoint: %w", closeZipErr)
	}
	if closeFileErr != nil {
		_ = os.Remove(archivePath)
		return "", fmt.Errorf("не удалось закрыть checkpoint: %w", closeFileErr)
	}
	return archivePath, nil
}

func resolveStatePath() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("не удалось определить путь программы: %w", err)
	}
	exe, err = filepath.Abs(exe)
	if err != nil {
		return "", fmt.Errorf("не удалось нормализовать путь программы: %w", err)
	}
	return filepath.Join(filepath.Dir(exe), stateFileName), nil
}

func loadState(path string) (State, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			state := defaultState()
			if saveErr := saveState(path, state); saveErr != nil {
				return State{}, fmt.Errorf("не удалось создать начальное состояние: %w", saveErr)
			}
			return state, nil
		}
		return State{}, fmt.Errorf("не удалось прочитать состояние: %w", err)
	}

	var state State
	if err := json.Unmarshal(data, &state); err != nil {
		return State{}, fmt.Errorf("повреждён файл состояния: %w", err)
	}
	if state.FormatVersion != 1 {
		return State{}, fmt.Errorf("неподдерживаемая версия состояния: %d", state.FormatVersion)
	}
	if state.LastUsedStep == nil {
		state.LastUsedStep = map[string]int{"F": 0, "S": 0, "D": 0}
	}
	return state, nil
}

func defaultState() State {
	return State{
		FormatVersion: 1,
		Step:          0,
		Registers:     RegisterSet{},
		Flow1: Flow{
			Text:     "Поток ещё не начат.",
			Question: "Какая мысль сейчас требует продолжения?",
		},
		LastUsedStep: map[string]int{"F": 0, "S": 0, "D": 0},
		History:      []HistoryEntry{},
	}
}

func saveState(path string, state State) error {
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("не удалось сериализовать состояние: %w", err)
	}
	data = append(data, '\n')

	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".eon-state-*.tmp")
	if err != nil {
		return fmt.Errorf("не удалось создать временный файл: %w", err)
	}
	tmpName := tmp.Name()
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.Remove(tmpName)
		}
	}()

	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("не удалось записать временный файл: %w", err)
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("не удалось синхронизировать временный файл: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("не удалось закрыть временный файл: %w", err)
	}

	backup := path + ".bak"
	_ = os.Remove(backup)

	hadOriginal := false
	if _, err := os.Stat(path); err == nil {
		hadOriginal = true
		if err := os.Rename(path, backup); err != nil {
			return fmt.Errorf("не удалось создать резервную копию состояния: %w", err)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("не удалось проверить существующий файл состояния: %w", err)
	}

	if err := os.Rename(tmpName, path); err != nil {
		if hadOriginal {
			_ = os.Rename(backup, path)
		}
		return fmt.Errorf("не удалось заменить файл состояния: %w", err)
	}
	cleanup = false

	if hadOriginal {
		_ = os.Remove(backup)
	}
	return nil
}

func availability(state State, currentStep int) map[string]bool {
	result := make(map[string]bool, 3)
	for _, level := range levels {
		last := state.LastUsedStep[level.Key]
		result[level.Key] = currentStep-last >= level.Interval
	}
	return result
}

func stepsUntilAvailable(state State, currentStep int, level levelInfo) int {
	last := state.LastUsedStep[level.Key]
	remaining := level.Interval - (currentStep - last)
	if remaining < 0 {
		return 0
	}
	return remaining
}

func printHeader(state State, currentStep int, available map[string]bool) {
	fmt.Printf("СИСТЕМА 20 — eonmem %s\n", appVersion)
	fmt.Printf("Шаг: %d\n\n", currentStep)
	fmt.Println("РЕГИСТРЫ")

	for _, level := range levels {
		fmt.Printf("\n%s\n", level.Title)
		values := registerArray(state.Registers, level.Key)
		for i, value := range values {
			if strings.TrimSpace(value) == "" {
				value = "—"
			}
			fmt.Printf("%s%d: %s\n", level.Key, i+1, value)
		}
		if available[level.Key] {
			fmt.Printf("Изменение %s: доступно\n", level.Key)
		} else {
			fmt.Printf("Изменение %s: через %d шаг(а)\n", level.Key, stepsUntilAvailable(state, currentStep, level))
		}
	}

	fmt.Println("\nТЕКУЩЕЕ РАЗМЫШЛЕНИЕ")
	fmt.Println("\nПоток 1")
	fmt.Println(state.Flow1.Text)
	fmt.Printf("\nТекущий вопрос потока 1:\n%s\n\n", state.Flow1.Question)
}

func registerArray(registers RegisterSet, level string) [3]string {
	switch level {
	case "D":
		return registers.D
	case "S":
		return registers.S
	default:
		return registers.F
	}
}

func promptLine(reader *bufio.Reader, prompt string, maxRunes int) (string, error) {
	for {
		fmt.Print(prompt)
		line, err := readRawLine(reader)
		if err != nil {
			return "", err
		}
		line = strings.TrimSpace(line)
		if line == "" {
			fmt.Println("Ввод не может быть пустым.")
			continue
		}
		count := utf8.RuneCountInString(line)
		if count > maxRunes {
			fmt.Printf("Слишком длинный ввод: %d/%d знаков. Повторите.\n", count, maxRunes)
			continue
		}
		return line, nil
	}
}

func readRawLine(reader *bufio.Reader) (string, error) {
	line, err := reader.ReadString('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		return "", fmt.Errorf("ошибка чтения ввода: %w", err)
	}
	if errors.Is(err, io.EOF) && len(line) == 0 {
		return "", errors.New("ввод завершился раньше времени")
	}
	return strings.TrimRight(line, "\r\n"), nil
}

func applyRegisterInput(state *State, line string, available map[string]bool) (RegisterChange, string, error) {
	parts := strings.SplitN(line, " ", 2)
	if len(parts) != 2 {
		return RegisterChange{}, "", errors.New("ожидается ключ и новое значение через пробел")
	}

	key := strings.ToUpper(strings.TrimSpace(parts[0]))
	value := strings.TrimSpace(parts[1])
	if len(key) != 2 || key[1] < '1' || key[1] > '3' {
		return RegisterChange{}, "", errors.New("ключ должен иметь вид F1, S2 или D3")
	}
	level := key[:1]
	if level != "F" && level != "S" && level != "D" {
		return RegisterChange{}, "", errors.New("неизвестный уровень регистра")
	}
	if !available[level] {
		return RegisterChange{}, "", fmt.Errorf("изменение уровня %s сейчас недоступно", level)
	}
	if value == "" {
		return RegisterChange{}, "", errors.New("новое значение не может быть пустым")
	}
	if count := utf8.RuneCountInString(value); count > maxRegisterLen {
		return RegisterChange{}, "", fmt.Errorf("значение слишком длинное: %d/%d знаков", count, maxRegisterLen)
	}

	index := int(key[1] - '1')
	old := getRegister(state.Registers, level, index)
	setRegister(&state.Registers, level, index, value)

	return RegisterChange{Key: key, Old: old, New: value}, level, nil
}

func getRegister(registers RegisterSet, level string, index int) string {
	switch level {
	case "D":
		return registers.D[index]
	case "S":
		return registers.S[index]
	default:
		return registers.F[index]
	}
}

func setRegister(registers *RegisterSet, level string, index int, value string) {
	switch level {
	case "D":
		registers.D[index] = value
	case "S":
		registers.S[index] = value
	case "F":
		registers.F[index] = value
	}
}

func copyAvailability(source map[string]bool) map[string]bool {
	result := make(map[string]bool, len(source))
	for key, value := range source {
		if value {
			result[key] = true
		}
	}
	return result
}

func formatAvailableLevels(available map[string]bool) string {
	keys := make([]string, 0, len(available))
	for _, key := range []string{"F", "S", "D"} {
		if available[key] {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	return strings.Join(keys, ", ")
}
